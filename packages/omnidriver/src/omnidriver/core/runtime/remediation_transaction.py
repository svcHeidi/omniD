"""Case-local journal for agent-proposed configuration transactions."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .transaction_mechanics import atomic_write_bytes as _atomic_write_bytes
from .transaction_mechanics import atomic_write_json as _atomic_write_json
from .transaction_mechanics import fsync_directory as _fsync_directory


MARKER_NAME = ".omnidriver-remediation-transaction.json"

#: The two directories this module writes under ``output_dir`` (for a
#: tutorial-record run, ``output_dir`` is ``case_root`` itself). Named once
#: here, alongside ``MARKER_NAME``, so core's run records
#: (``core.runtime_records``) can name all three (R1 fix, finding I3: the
#: marker and ``TRANSACTIONS_DIRECTORY`` were missing from
#: ``CORE_RUNTIME_RECORDS``; ``CANDIDATES_DIRECTORY`` -- written by
#: ``_archive_candidate_files`` -- was missing from that fix's own plan too).
TRANSACTIONS_DIRECTORY = "remediation_transactions"
CANDIDATES_DIRECTORY = "remediation_candidates"


class RemediationTransactionError(RuntimeError):
    """A case has an interrupted or rejected configuration transaction."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marker(case_root: Path) -> Path:
    return Path(case_root) / MARKER_NAME


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """Phase 2 Task 12: delegates to the primitive
    :mod:`transaction_mechanics` and :mod:`case_transaction` now share --
    what "goes away" here is the duplicate write-tmp/fsync/rename/fsync-dir
    implementation this function used to carry itself."""
    _atomic_write_json(path, payload)


def _persist(case_root: Path, transaction: dict[str, Any]) -> None:
    """Update the case head and the durable record for this transaction."""
    _atomic_write(_marker(case_root), transaction)
    output_dir = Path(str(transaction["output_dir"]))
    record = (
        output_dir / TRANSACTIONS_DIRECTORY
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
        "applying", "validated", "dispatching", "accepted", "rejected", "rolled_back",
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
    if status in {"applying", "validated", "dispatching"}:
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
    repair_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(case_root).resolve()
    output = Path(output_dir).resolve()
    _require_transaction_ownership(root, output)
    previous = read_remediation_transaction(root)
    if previous is not None and previous["status"] in {
        "applying", "validated", "dispatching",
    }:
        require_reusable_case(case_root, explicit_repair=True)
    proposal_payload = {"hypothesis": hypothesis, "overrides": overrides}
    try:
        proposal_json = json.dumps(
            proposal_payload, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RemediationTransactionError(
            "remediation proposal must contain strict JSON values"
        ) from exc
    proposal_digest = "sha256:" + hashlib.sha256(proposal_json.encode()).hexdigest()
    binding = _validated_repair_binding(repair_binding, proposal_digest)
    previous_binding = previous.get("repair_binding") if previous else None
    previous_execution = (
        previous_binding.get("execution") if isinstance(previous_binding, dict) else None
    )
    if (
        binding is not None
        and isinstance(previous_binding, dict)
        and previous_binding.get("loop_id") == binding["loop_id"]
        and isinstance(previous_execution, int)
        and previous_execution >= binding["execution"]
    ):
        raise RemediationTransactionError(
            "repair reservation is duplicate or older than the current transaction"
        )
    baseline_status = previous.get("status") if previous else None
    if baseline_status == "rolled_back":
        baseline_status = previous.get("baseline_status")
    transaction = {
        "schema_version": 2,
        "revision": 1,
        "transaction_id": str(uuid.uuid4()),
        "origin": "repair_loop" if binding is not None else "manual",
        "status": "applying",
        "started_at": _now(),
        "step_id": step_id,
        "output_dir": str(output),
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
    if binding is not None:
        transaction["repair_binding"] = binding
    transaction["target_manifest"] = _snapshot_targets(
        root, transaction, target_paths,
    )
    _persist(root, transaction)
    return transaction


def _validated_repair_binding(
    binding: Mapping[str, Any] | None,
    proposal_digest: str,
) -> dict[str, Any] | None:
    if binding is None:
        return None
    expected_keys = {
        "loop_id", "execution", "reservation_id",
        "observation_digest", "proposal_digest",
    }
    if set(binding) != expected_keys:
        raise RemediationTransactionError("repair reservation binding is malformed")
    try:
        loop_id = str(uuid.UUID(str(binding["loop_id"])))
        reservation_id = str(uuid.UUID(str(binding["reservation_id"])))
    except (ValueError, AttributeError) as exc:
        raise RemediationTransactionError("repair reservation binding is malformed") from exc
    execution = binding["execution"]
    if isinstance(execution, bool) or not isinstance(execution, int) or execution < 1:
        raise RemediationTransactionError("repair reservation execution must be positive")
    observation_digest = binding["observation_digest"]
    bound_proposal_digest = binding["proposal_digest"]
    if not isinstance(observation_digest, str) or not observation_digest.startswith("sha256:"):
        raise RemediationTransactionError("repair observation digest is malformed")
    if bound_proposal_digest != proposal_digest:
        raise RemediationTransactionError(
            "repair reservation proposal digest does not match the transaction proposal"
        )
    return {
        "loop_id": loop_id,
        "execution": execution,
        "reservation_id": reservation_id,
        "observation_digest": observation_digest,
        "proposal_digest": bound_proposal_digest,
    }


def restore_remediation_transaction(
    case_root: Path,
    *,
    output_dir: Path,
    transaction_id: str,
    expected_revision: int,
    expected_status: str,
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
    if (
        transaction_id != current_id
        or expected_revision != int(transaction.get("revision", 0))
        or expected_status != transaction.get("status")
    ):
        raise RemediationTransactionError(
            "remediation restore compare-and-swap conflict"
        )
    if Path(str(transaction.get("output_dir", ""))).resolve() != output:
        raise RemediationTransactionError(
            "transaction output directory does not match the owned restore output"
        )
    if transaction["status"] == "rolled_back" and transaction.get("recovered_at"):
        return transaction
    if transaction["status"] not in {"applying", "validated", "dispatching", "rejected"}:
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
        "revision": int(transaction.get("revision", 0)) + 1,
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
    repair_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in {"validated", "rejected", "rolled_back"}:
        raise ValueError(f"invalid remediation transaction status: {status}")
    root, _output, current = _current_transition(
        case_root, transaction, expected_statuses={"applying"},
    )
    if status == "rolled_back" and not baseline_is_restored(
        root, current, output_dir=Path(str(current["output_dir"])),
    ):
        raise RemediationTransactionError(
            "transaction cannot be marked rolled_back until its exact baseline is restored"
        )
    updated = {
        **current,
        "revision": int(current["revision"]) + 1,
        "status": status,
        "validated_at": _now() if status == "validated" else None,
        "finished_at": _now() if status != "validated" else None,
        "effective_resolution": list(effective_resolution),
        "plan_digest": plan_digest,
        "error": error,
    }
    if repair_result is not None:
        if status == "validated":
            raise RemediationTransactionError(
                "a validated transaction cannot carry a terminal repair result"
            )
        validated_result = _validated_terminal_repair_result(repair_result)
        if validated_result["status"] != "rejected":
            raise RemediationTransactionError(
                "a pre-dispatch terminal transaction requires a rejected repair result"
            )
        updated["repair_result"] = validated_result
    elif current.get("repair_binding") is not None and status != "validated":
        raise RemediationTransactionError(
            "a terminal repair transaction requires its resulting observation"
        )
    if status == "rejected":
        archive = _archive_candidate_files(root, updated)
        if archive is not None:
            updated["candidate_archive"] = str(archive)
    if updated.get("repair_binding") is not None and status != "validated":
        from .repair_loop import commit_repair_transaction_witness

        commit_repair_transaction_witness(_output, updated)
    _persist(root, updated)
    return updated


def mark_remediation_dispatching(
    case_root: Path, transaction: dict[str, Any],
) -> dict[str, Any]:
    """Record dispatch admission; the candidate is still not reusable."""
    root, _output, current = _current_transition(
        case_root, transaction, expected_statuses={"validated"},
    )
    updated = {
        **current,
        "revision": int(current["revision"]) + 1,
        "status": "dispatching",
        "dispatch_started_at": _now(),
    }
    _persist(root, updated)
    return updated


def record_remediation_outcome(
    case_root: Path,
    transaction: dict[str, Any],
    *,
    execution_status: str,
    attempt: int,
    repair_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root, _output, current = _current_transition(
        case_root, transaction, expected_statuses={"dispatching"},
    )
    terminal_status = "accepted" if execution_status == "ok" else "rejected"
    updated = {
        **current,
        "revision": int(current["revision"]) + 1,
        "status": terminal_status,
        "finished_at": _now(),
        "execution_status": execution_status,
        "execution_attempt": attempt,
        "execution_finished_at": _now(),
    }
    if repair_result is not None:
        validated_result = _validated_terminal_repair_result(repair_result)
        expected_result = "succeeded" if execution_status == "ok" else "failed"
        if validated_result["status"] != expected_result:
            raise RemediationTransactionError(
                "repair result status does not match the execution outcome"
            )
        updated["repair_result"] = validated_result
    elif current.get("repair_binding") is not None:
        raise RemediationTransactionError(
            "a terminal repair transaction requires its resulting observation"
        )
    if terminal_status == "rejected":
        archive = _archive_candidate_files(root, updated)
        if archive is not None:
            updated["candidate_archive"] = str(archive)
    if updated.get("repair_binding") is not None:
        from .repair_loop import commit_repair_transaction_witness

        commit_repair_transaction_witness(_output, updated)
    _persist(root, updated)
    return updated


def _validated_terminal_repair_result(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    if set(result) != {"status", "observation", "observation_digest"}:
        raise RemediationTransactionError("terminal repair result is malformed")
    if result["status"] not in {"succeeded", "failed", "rejected"}:
        raise RemediationTransactionError("terminal repair result status is invalid")
    if not isinstance(result["observation"], dict):
        raise RemediationTransactionError("terminal repair observation is malformed")
    try:
        canonical = json.dumps(
            result["observation"], sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RemediationTransactionError(
            "terminal repair observation must contain strict JSON values"
        ) from exc
    digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    if result["observation_digest"] != digest:
        raise RemediationTransactionError("terminal repair observation digest mismatch")
    return {
        "status": result["status"],
        "observation": result["observation"],
        "observation_digest": digest,
    }


def reconcile_terminal_remediation_record(
    case_root: Path,
    *,
    output_dir: Path,
    repair_binding: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Repair a torn output mirror from the authoritative terminal case head."""
    root = Path(case_root).resolve()
    output = Path(output_dir).resolve()
    _require_transaction_ownership(root, output)
    transaction = read_remediation_transaction(root)
    if transaction is None or transaction.get("repair_binding") != dict(repair_binding):
        return None
    if Path(str(transaction.get("output_dir", ""))).resolve() != output:
        raise RemediationTransactionError(
            "terminal remediation output identity does not match its reservation"
        )
    status = transaction.get("status")
    result = transaction.get("repair_result")
    if status not in {"accepted", "rejected", "rolled_back"} or not isinstance(result, dict):
        return None
    validated_result = _validated_terminal_repair_result(result)
    expected = {
        "accepted": "succeeded",
        "rejected": "failed" if "execution_status" in transaction else "rejected",
        "rolled_back": "rejected",
    }[status]
    if validated_result["status"] != expected:
        raise RemediationTransactionError(
            "terminal remediation result contradicts the case head status"
        )
    record = output / "remediation_transactions" / f"{transaction['transaction_id']}.json"
    try:
        mirrored = json.loads(record.read_text())
    except (OSError, json.JSONDecodeError):
        mirrored = None
    if mirrored != transaction:
        _atomic_write(record, transaction)
    return transaction


def reconcile_committed_repair_transaction(
    case_root: Path,
    *,
    output_dir: Path,
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize a stable terminal witness after any torn journal write."""
    root = Path(case_root).resolve()
    output = Path(output_dir).resolve()
    _require_transaction_ownership(root, output)
    committed = dict(transaction)
    if Path(str(committed.get("output_dir", ""))).resolve() != output:
        raise RemediationTransactionError("committed repair output identity mismatch")
    if not isinstance(committed.get("repair_binding"), dict):
        raise RemediationTransactionError("committed repair binding is missing")
    result = committed.get("repair_result")
    if not isinstance(result, dict):
        raise RemediationTransactionError("committed repair result is missing")
    validated_result = _validated_terminal_repair_result(result)
    status = committed.get("status")
    expected_result = {
        "accepted": "succeeded",
        "rejected": "failed" if "execution_status" in committed else "rejected",
        "rolled_back": "rejected",
    }.get(status)
    if expected_result is None or validated_result["status"] != expected_result:
        raise RemediationTransactionError("committed repair terminal status is inconsistent")

    current = read_remediation_transaction(root)
    if current is None:
        raise RemediationTransactionError("committed repair case head is missing")
    if current.get("transaction_id") == committed.get("transaction_id"):
        if current == committed:
            pass
        elif (
            int(current.get("revision", 0)) + 1 == int(committed.get("revision", 0))
            and current.get("status")
            == ("dispatching" if status in {"accepted", "rejected"} and "execution_status" in committed else "applying")
        ):
            _persist(root, committed)
            return committed
        else:
            raise RemediationTransactionError(
                "committed repair witness conflicts with its case head"
            )
    record = output / "remediation_transactions" / f"{committed['transaction_id']}.json"
    try:
        mirrored = json.loads(record.read_text())
    except (OSError, json.JSONDecodeError):
        mirrored = None
    if mirrored != committed:
        _atomic_write(record, committed)
    return committed


def _require_transaction_ownership(root: Path, output: Path) -> None:
    from .attempt_lease import attempt_lease_is_held, case_lease_is_held

    if not case_lease_is_held(root) or not attempt_lease_is_held(output):
        raise RemediationTransactionError(
            "remediation transaction mutation requires owned case and output leases"
        )


def _current_transition(
    case_root: Path,
    expected: dict[str, Any],
    *,
    expected_statuses: set[str],
) -> tuple[Path, Path, dict[str, Any]]:
    root = Path(case_root).resolve()
    output = Path(str(expected.get("output_dir", ""))).resolve()
    _require_transaction_ownership(root, output)
    current = read_remediation_transaction(root)
    if current is None:
        raise RemediationTransactionError("remediation transaction head is missing")
    if (
        current.get("transaction_id") != expected.get("transaction_id")
        or current.get("revision") != expected.get("revision")
        or current.get("status") != expected.get("status")
    ):
        raise RemediationTransactionError(
            "remediation transaction compare-and-swap conflict"
        )
    if current.get("status") not in expected_statuses:
        raise RemediationTransactionError(
            f"remediation transaction status {current.get('status')!r} cannot transition"
        )
    if Path(str(current.get("output_dir", ""))).resolve() != output:
        raise RemediationTransactionError("remediation transaction output identity changed")
    return root, output, current


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
    archive = output_dir / CANDIDATES_DIRECTORY / str(transaction["transaction_id"])
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
