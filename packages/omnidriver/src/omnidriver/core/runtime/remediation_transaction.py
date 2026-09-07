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
    _persist(case_root, transaction)
    return transaction


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
        resolution = transaction.get("effective_resolution", ())
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
    copied = False
    for item in transaction.get("effective_resolution", ()):
        if not isinstance(item, dict):
            continue
        for raw_path in item.get("inspected_files", ()):
            source = Path(str(raw_path)).resolve()
            if not source.is_file() or not source.is_relative_to(root):
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
