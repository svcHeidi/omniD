"""Case-local journal for agent-proposed configuration transactions."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MARKER_NAME = ".omnidriver-remediation-transaction.json"


class RemediationTransactionError(RuntimeError):
    """A case has an interrupted or rejected configuration transaction."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marker(case_root: Path) -> Path:
    return Path(case_root) / MARKER_NAME


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, content: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _persist(case_root: Path, transaction: dict[str, Any]) -> None:
    """Update the case head and the durable record for this transaction."""
    _atomic_write(_marker(case_root), transaction)
    output_dir = Path(str(transaction["output_dir"]))
    record = (
        output_dir / "remediation_transactions"
        / f"{transaction['transaction_id']}.json"
    )
    _atomic_write(record, transaction)


def read_remediation_transaction(case_root: Path) -> dict[str, Any] | None:
    path = _marker(case_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RemediationTransactionError(
            f"remediation transaction marker is unreadable: {path}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("status") not in {
        "applying", "accepted", "rejected", "rolled_back",
    }:
        raise RemediationTransactionError(
            f"remediation transaction marker is malformed: {path}"
        )
    return payload


def require_reusable_case(case_root: Path, *, explicit_repair: bool) -> None:
    """Block silent reuse of an interrupted or rejected candidate."""
    transaction = read_remediation_transaction(case_root)
    if transaction is None:
        return
    status = transaction["status"]
    effective_status = (
        transaction.get("baseline_status") if status == "rolled_back" else status
    )
    transaction_id = transaction.get("transaction_id", "unknown")
    if status == "applying":
        raise RemediationTransactionError(
            f"configuration transaction {transaction_id} was interrupted; "
            "restore/restage the case before execution"
        )
    if effective_status == "rejected" and not explicit_repair:
        raise RemediationTransactionError(
            f"configuration transaction {transaction_id} was rejected; "
            "provide a new explicit --apply repair or restore/restage the case"
        )


def begin_remediation_transaction(
    case_root: Path,
    *,
    output_dir: Path,
    step_id: str,
    overrides: list[dict[str, Any]],
    hypothesis: str | None,
    target_paths: tuple[Path, ...],
) -> dict[str, Any]:
    previous = read_remediation_transaction(case_root)
    if previous is not None and previous["status"] == "applying":
        require_reusable_case(case_root, explicit_repair=True)
    proposal_payload = {"hypothesis": hypothesis, "overrides": overrides}
    proposal_digest = "sha256:" + hashlib.sha256(
        json.dumps(proposal_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    baseline_status = previous.get("status") if previous else None
    if baseline_status == "rolled_back":
        baseline_status = previous.get("baseline_status")
    transaction = {
        "schema_version": 1,
        "transaction_id": str(uuid.uuid4()),
        "status": "applying",
        "started_at": _now(),
        "step_id": step_id,
        "output_dir": str(Path(output_dir).resolve()),
        "hypothesis": hypothesis,
        "overrides": overrides,
        "proposal_digest": proposal_digest,
        "parent_transaction_id": previous.get("transaction_id") if previous else None,
        "baseline_status": baseline_status,
        "baseline_effective_resolution": (
            previous.get("effective_resolution", ())
            if previous and previous.get("status") == "accepted"
            else previous.get("baseline_effective_resolution", ()) if previous else ()
        ),
        "repeats_failed_proposal": bool(
            previous
            and previous.get("proposal_digest") == proposal_digest
            and previous.get("execution_status") in {"failed", "error"}
        ),
    }
    transaction["target_manifest"] = _snapshot_targets(
        case_root, transaction, target_paths,
    )
    _persist(case_root, transaction)
    return transaction


def restore_remediation_transaction(
    case_root: Path,
    *,
    output_dir: Path,
    transaction_id: str | None = None,
) -> dict[str, Any]:
    """Restore exact before-images for the current interrupted/rejected edit."""
    from .attempt_lease import attempt_lease_is_held, case_lease_is_held

    root = Path(case_root).resolve()
    output = Path(output_dir).resolve()
    if not case_lease_is_held(root) or not attempt_lease_is_held(output):
        raise RemediationTransactionError(
            "remediation restore requires owned case and output leases"
        )
    transaction = read_remediation_transaction(root)
    if transaction is None:
        raise RemediationTransactionError("case has no remediation transaction to restore")
    current_id = str(transaction.get("transaction_id", ""))
    if transaction_id is not None and transaction_id != current_id:
        raise RemediationTransactionError(
            f"transaction id {transaction_id!r} is not the current transaction {current_id!r}"
        )
    if Path(str(transaction.get("output_dir", ""))).resolve() != output:
        raise RemediationTransactionError(
            "transaction output directory does not match the owned restore output"
        )
    if transaction["status"] == "rolled_back" and transaction.get("recovered_at"):
        return transaction
    if transaction["status"] not in {"applying", "rejected"}:
        raise RemediationTransactionError(
            f"transaction {current_id} has status {transaction['status']!r}, not recoverable"
        )

    validated = _validated_manifest(root, output, transaction)
    recovery_id = str(uuid.uuid4())
    candidate_dir = (
        output / "remediation_candidates" / current_id
        / f"before_restore.{recovery_id}"
    )
    candidate_manifest = _snapshot_paths(root, candidate_dir, tuple(path for path, _ in validated))
    _atomic_write(candidate_dir / "manifest.json", {"targets": candidate_manifest})

    for target, item in validated:
        if item["kind"] == "absent":
            if target.is_dir() and not target.is_symlink():
                raise RemediationTransactionError(
                    f"restore target unexpectedly became a directory: {target}"
                )
            target.unlink(missing_ok=True)
            _fsync_directory(target.parent)
            continue
        backup = output / str(item["backup_relpath"])
        _atomic_write_bytes(target, backup.read_bytes(), mode=int(item["mode"]))

    restored = {
        **transaction,
        "status": "rolled_back",
        "finished_at": _now(),
        "recovered_at": _now(),
        "recovery_mode": "restore_before_images",
        "candidate_archive": str(candidate_dir),
        "restored_targets": [str(path.relative_to(root)) for path, _ in validated],
    }
    _persist(root, restored)
    return restored


def baseline_is_restored(
    case_root: Path, transaction: dict[str, Any], *, output_dir: Path,
) -> bool:
    """Whether every target still exactly matches its durable before-image."""
    try:
        validated = _validated_manifest(
            Path(case_root).resolve(), Path(output_dir).resolve(), transaction,
        )
    except RemediationTransactionError:
        return False
    for target, item in validated:
        if item["kind"] == "absent":
            if target.exists() or target.is_symlink():
                return False
            continue
        try:
            content = target.read_bytes()
            mode = target.stat().st_mode & 0o7777
        except OSError:
            return False
        if (
            hashlib.sha256(content).hexdigest() != item["sha256"]
            or mode != int(item["mode"])
        ):
            return False
    return True


def finish_remediation_transaction(
    case_root: Path,
    transaction: dict[str, Any],
    *,
    status: str,
    effective_resolution: tuple[dict[str, Any], ...] = (),
    plan_digest: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if status not in {"accepted", "rejected", "rolled_back"}:
        raise ValueError(f"invalid remediation transaction status: {status}")
    updated = {
        **transaction,
        "status": status,
        "finished_at": _now(),
        "effective_resolution": list(effective_resolution),
        "plan_digest": plan_digest,
        "error": error,
    }
    if status == "rejected":
        archive = _archive_candidate_files(case_root, updated)
        if archive is not None:
            updated["candidate_archive"] = str(archive)
    _persist(case_root, updated)
    return updated


def record_remediation_outcome(
    case_root: Path,
    transaction: dict[str, Any],
    *,
    execution_status: str,
    attempt: int,
) -> dict[str, Any]:
    updated = {
        **transaction,
        "execution_status": execution_status,
        "execution_attempt": attempt,
        "execution_finished_at": _now(),
    }
    _persist(case_root, updated)
    return updated


def accepted_external_dependencies(case_root: Path) -> tuple[Path, ...]:
    """External files inspected by the accepted effective configuration."""
    transaction = read_remediation_transaction(case_root)
    if transaction is None:
        return ()
    if transaction["status"] == "accepted":
        resolution = (
            *transaction.get("baseline_effective_resolution", ()),
            *transaction.get("effective_resolution", ()),
        )
    elif (
        transaction["status"] == "rolled_back"
        and transaction.get("baseline_status") == "accepted"
    ):
        resolution = transaction.get("baseline_effective_resolution", ())
    else:
        return ()
    root = Path(case_root).resolve()
    dependencies: set[Path] = set()
    for item in resolution:
        if not isinstance(item, dict):
            continue
        for raw_path in item.get("inspected_files", ()):
            path = Path(str(raw_path)).resolve()
            if not path.is_relative_to(root):
                dependencies.add(path)
    return tuple(sorted(dependencies))


def _archive_candidate_files(
    case_root: Path, transaction: dict[str, Any],
) -> Path | None:
    output_dir = Path(str(transaction["output_dir"]))
    archive = output_dir / "remediation_candidates" / str(transaction["transaction_id"])
    root = Path(case_root).resolve()
    sources: set[Path] = set()
    for item in transaction.get("target_manifest", ()):
        if not isinstance(item, dict):
            continue
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            continue
        sources.add(root / relative)
    copied = False
    for item in transaction.get("effective_resolution", ()):
        if not isinstance(item, dict):
            continue
        for raw_path in item.get("inspected_files", ()):
            source = Path(str(raw_path)).resolve()
            if source.is_relative_to(root):
                sources.add(source)
    for source in sorted(sources):
        if (
            not source.is_file()
            or source.is_symlink()
            or not source.parent.resolve().is_relative_to(root)
        ):
            continue
        destination = archive / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied = True
    if copied:
        (archive / "transaction.json").write_text(
            json.dumps(transaction, indent=2, sort_keys=True) + "\n"
        )
        return archive
    return None


def _snapshot_targets(
    case_root: Path,
    transaction: dict[str, Any],
    target_paths: tuple[Path, ...],
) -> list[dict[str, Any]]:
    root = Path(case_root).resolve()
    output = Path(str(transaction["output_dir"])).resolve()
    backup_dir = (
        output / "remediation_transactions" / str(transaction["transaction_id"])
        / "before"
    )
    manifest = _snapshot_paths(root, backup_dir, target_paths)
    _atomic_write(backup_dir.parent / "manifest.json", {"targets": manifest})
    return manifest


def _snapshot_paths(
    root: Path, backup_dir: Path, target_paths: tuple[Path, ...],
) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_target in target_paths:
        target = Path(raw_target)
        if not target.is_absolute():
            target = root / target
        absolute = Path(os.path.abspath(target))
        try:
            relative = absolute.relative_to(root)
        except ValueError as exc:
            raise RemediationTransactionError(
                f"override target escapes case root: {target}"
            ) from exc
        relpath = relative.as_posix()
        if relpath in seen:
            continue
        seen.add(relpath)
        if not absolute.parent.resolve().is_relative_to(root):
            raise RemediationTransactionError(
                f"override target parent escapes case root: {target}"
            )
        if absolute.is_symlink():
            raise RemediationTransactionError(
                f"crash-safe override targets may not be symlinks: {target}"
            )
        if not absolute.exists():
            manifest.append({"path": relpath, "kind": "absent"})
            continue
        if not absolute.is_file():
            raise RemediationTransactionError(
                f"override target is not a regular file: {target}"
            )
        content = absolute.read_bytes()
        backup = backup_dir / relative
        _atomic_write_bytes(backup, content, mode=absolute.stat().st_mode & 0o7777)
        manifest.append({
            "path": relpath,
            "kind": "file",
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": absolute.stat().st_mode & 0o7777,
            "backup_relpath": str(backup.relative_to(Path(backup_dir).parents[2])),
        })
    return manifest


def _validated_manifest(
    root: Path, output: Path, transaction: dict[str, Any],
) -> list[tuple[Path, dict[str, Any]]]:
    manifest = transaction.get("target_manifest")
    if not isinstance(manifest, list) or not manifest:
        raise RemediationTransactionError("transaction has no restorable target manifest")
    validated: list[tuple[Path, dict[str, Any]]] = []
    for item in manifest:
        if not isinstance(item, dict) or item.get("kind") not in {"file", "absent"}:
            raise RemediationTransactionError("transaction target manifest is malformed")
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise RemediationTransactionError("transaction target path is unsafe")
        target = root / relative
        if not target.parent.resolve().is_relative_to(root) or target.is_symlink():
            raise RemediationTransactionError(f"restore target is unsafe: {target}")
        if item["kind"] == "file":
            backup_rel = Path(str(item.get("backup_relpath", "")))
            if backup_rel.is_absolute() or ".." in backup_rel.parts:
                raise RemediationTransactionError("transaction backup path is unsafe")
            expected_backup = (
                output / "remediation_transactions"
                / str(transaction.get("transaction_id", "")) / "before" / relative
            )
            expected_rel = expected_backup.relative_to(output)
            if backup_rel != expected_rel:
                raise RemediationTransactionError(
                    "transaction backup path does not match its target"
                )
            backup = expected_backup
            if backup.is_symlink() or not backup.is_file():
                raise RemediationTransactionError(
                    f"transaction backup is unavailable: {backup}"
                )
            try:
                content = backup.read_bytes()
            except OSError as exc:
                raise RemediationTransactionError(
                    f"transaction backup is unavailable: {backup}"
                ) from exc
            if hashlib.sha256(content).hexdigest() != item.get("sha256"):
                raise RemediationTransactionError(
                    f"transaction backup hash mismatch: {backup}"
                )
        validated.append((target, item))
    return validated
