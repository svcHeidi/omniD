"""Commit a reviewed plan's bytes recoverably: atomic per-file replacement, a before-image journal, rollback.

The only module that writes a framework-authored case input; it moves bytes and digests and knows no dictionary syntax.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

from .case_write import (
    CaseWritePlan,
    CaseWriteRecord,
    RenderedFile,
    _digest_bytes,
)
from .runtime.attempt_lease import AttemptLeaseError, acquire_case_lease, case_lease_is_held
from .runtime.transaction_mechanics import (
    atomic_write_bytes as _atomic_write_bytes,
    atomic_write_json as _atomic_write_json,
    fsync_directory as _fsync_directory,
)

# Not guaranteed: simultaneous visibility of several files to an outside reader
# (a multi-file commit can be seen half done), control over writers outside the
# framework, or durability beyond fsync of the file and its directory on a local
# POSIX filesystem. A symlinked write target is refused outright.

#: The transaction's authoritative head is the journal file. Legal states and
#: who may advance them:
#:
#: ``planning``    no journal. Nothing has been written.
#: ``preparing``   journal written, no file replaced yet. Recovery: delete the
#:                 journal; nothing was changed.
#: ``applying``    at least one file replaced. Recovery: restore every
#:                 before-image in the journal, then delete it.
#: ``committed``   every file replaced, journal removed. Terminal.
#: ``rolled_back`` recovery completed. Terminal.
#:
#: There is one head and one recovery owner: whoever holds the case lease. A
#: journal in ``applying`` (or ``preparing``) blocks dispatch of a new
#: transaction until recovery runs -- an unrecovered case is not a case whose
#: inputs are known.
TRANSACTION_STATES = ("planning", "preparing", "applying", "committed", "rolled_back")

_JOURNAL_SCHEMA_VERSION = 1

#: Relative to a case root. A sibling of the case content rather than a
#: temp-directory record, for the same reason the case lease lives
#: case-adjacent: recovery must find this from the case alone, with nothing
#: else supplied.
_JOURNAL_RELATIVE_PATH = Path(".omnidriver") / "case-transaction.json"
_COMPLETED_DIRNAME = "case-transactions"


class CaseTransactionError(RuntimeError):
    """A commit was refused, or a rollback could not be completed cleanly."""


# --------------------------------------------------------------------------
# Journal: the transaction head
# --------------------------------------------------------------------------


def _journal_path(case_root: Path) -> Path:
    return Path(case_root) / _JOURNAL_RELATIVE_PATH


def _write_journal(case_root: Path, transaction: Mapping[str, Any]) -> None:
    """Persist the transaction head atomically, before the first file write."""
    _atomic_write_json(_journal_path(case_root), dict(transaction))


def _read_journal(case_root: Path) -> dict[str, Any] | None:
    path = _journal_path(case_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseTransactionError(
            f"case transaction journal is unreadable: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise CaseTransactionError(f"case transaction journal is malformed: {path}")
    # A corrupted or hand-edited journal with a bogus `state` must not be
    # read as though it were legitimate.
    if payload.get("state") not in TRANSACTION_STATES:
        raise CaseTransactionError(
            f"case transaction journal at {path} has state "
            f"{payload.get('state')!r}, not one of {TRANSACTION_STATES}; "
            f"refusing to treat an unrecognised journal as recoverable"
        )
    return payload


def pending_transaction(case_root: Path) -> Mapping[str, Any] | None:
    """The unrecovered transaction journal for this case, if any."""
    return _read_journal(case_root)


def _remove_journal(case_root: Path) -> None:
    _journal_path(case_root).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Completed-transaction record: what makes replay idempotent
# --------------------------------------------------------------------------


def _completed_path(case_root: Path, transaction_id: str) -> Path:
    return Path(case_root) / ".omnidriver" / _COMPLETED_DIRNAME / f"{transaction_id}.json"


def _read_completed(case_root: Path, transaction_id: str) -> dict[str, Any] | None:
    path = _completed_path(case_root, transaction_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseTransactionError(
            f"completed transaction record is unreadable: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise CaseTransactionError(f"completed transaction record is malformed: {path}")
    return payload


def _persist_completed(case_root: Path, record: CaseWriteRecord) -> None:
    _atomic_write_json(_completed_path(case_root, record.transaction_id), record.to_json())


def _record_from_completed(payload: Mapping[str, Any]) -> CaseWriteRecord:
    return CaseWriteRecord(
        transaction_id=payload["transaction_id"],
        plan_id=payload["plan_id"],
        plan_digest=payload["plan_digest"],
        committed=tuple(payload.get("committed", ())),
        evidence=tuple(payload.get("evidence", ())),
        status=payload.get("status", "committed"),
        parameters=tuple(payload.get("parameters", ())),
        expected_effects=tuple(payload.get("expected_effects", ())),
    )


def _check_render_exists_before(
    files: tuple[RenderedFile, ...], targets: Mapping[str, Path],
) -> None:
    """Refuse an ``exists_before`` claim the disk contradicts: a renderer that thought a document new would drop its sibling keys."""
    for rendered in files:
        target = targets[rendered.path]
        actually_exists = target.is_file()
        if rendered.exists_before != actually_exists:
            raise CaseTransactionError(
                f"rendered file {rendered.path!r} claims exists_before="
                f"{rendered.exists_before!r}, but the target "
                f"{'exists' if actually_exists else 'does not exist'} on "
                f"disk ({target}); the renderer's snapshot disagreed with "
                f"the real case -- refusing rather than trusting a wrong "
                f"'this file is new' claim that would silently discard "
                f"every other key already in it"
            )


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------


def _resolve_target(case_root: Path, rendered_path: str) -> Path:
    """The path to write; a symlink can move a legal spelling outside the case between planning and commit."""
    root = Path(case_root).resolve()
    candidate = Path(case_root) / rendered_path
    if candidate.is_symlink():
        raise CaseTransactionError(
            f"{rendered_path!r} is a symlink; refusing to write through it"
        )
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise CaseTransactionError(
            f"{rendered_path!r} resolves outside the case root via a "
            f"symlink in an ancestor directory: {resolved}"
        ) from None
    return candidate


# --------------------------------------------------------------------------
# Per-file mechanics
# --------------------------------------------------------------------------


def _before_image(rendered: RenderedFile, target: Path) -> dict[str, Any]:
    if target.exists() and not target.is_dir():
        try:
            content = target.read_bytes()
            mode = target.stat().st_mode & 0o7777
        except OSError as exc:
            raise CaseTransactionError(
                f"cannot read {rendered.path!r} to record its before-image "
                f"before overwriting it: {exc}"
            ) from exc
        return {
            "path": rendered.path,
            "existed_before": True,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "mode": mode,
        }
    return {
        "path": rendered.path,
        "existed_before": False,
        "content_base64": None,
        "mode": None,
    }


def _write_one(target: Path, rendered: RenderedFile) -> dict[str, Any]:
    """Replace one file atomically and return its committed entry."""
    _atomic_write_bytes(target, rendered.content, mode=rendered.mode)
    _fsync_directory(target.parent)
    return {"path": rendered.path, "content_digest": rendered.content_digest}


def _restore_one(target: Path, before_image: Mapping[str, Any]) -> None:
    """Idempotent, so recovery replays every before-image without knowing how far the commit got."""
    if before_image.get("existed_before"):
        content = base64.b64decode(before_image["content_base64"])
        _atomic_write_bytes(target, content, mode=before_image.get("mode"))
        _fsync_directory(target.parent)
    else:
        target.unlink(missing_ok=True)
        if target.parent.exists():
            _fsync_directory(target.parent)


def _all_missing_ancestors(case_root: Path, targets: list) -> list:
    """Directories that do not exist yet, deepest first, so rollback removes only those this transaction creates."""
    root = Path(case_root)
    seen: set = set()
    for target in targets:
        current = target.parent
        while current != root and not current.exists():
            seen.add(current.relative_to(root).as_posix())
            current = current.parent
    return sorted(seen, key=lambda relpath: relpath.count("/"), reverse=True)


def _remove_created_directories(case_root: Path, journal: Mapping[str, Any]) -> None:
    root = Path(case_root)
    for relpath in journal.get("created_dirs", ()):
        try:
            (root / relpath).rmdir()
        except OSError:
            # Not empty (something else legitimately lives there) or already
            # gone. Either way, forcing it is not this function's job.
            pass


def _rollback(case_root: Path, journal: Mapping[str, Any]) -> None:
    """Restore every before-image; on any failure keep the journal and raise naming every path that failed."""
    root = Path(case_root)
    failures: list[tuple[str, Exception]] = []
    for image in journal.get("before_images", ()):
        target = root / image["path"]
        try:
            _restore_one(target, image)
        except Exception as exc:  # noqa: BLE001 - collected, not swallowed
            failures.append((image["path"], exc))
    if failures:
        detail = "; ".join(f"{path}: {exc}" for path, exc in failures)
        raise CaseTransactionError(
            f"rollback failed restoring {[path for path, _ in failures]}; the "
            f"journal was left in place so the case's prior state remains "
            f"recoverable: {detail}"
        )
    _remove_created_directories(case_root, journal)
    _remove_journal(case_root)


# --------------------------------------------------------------------------
# Stack freshness
# --------------------------------------------------------------------------


def _check_stack_freshness(plan: CaseWritePlan, driver_context: Any) -> None:
    """Refuse a plan bound to a stack that is no longer the composed one."""
    # Applies only when the context carries a StackIdentity. Most contract
    # members contribute a placeholder digest, so this catches a changed
    # provider set, version, profile, vocabulary or manifest, not an edited
    # renderer in an editable install.
    identity = getattr(driver_context, "identity", None)
    if identity is None:
        return
    current_digest = getattr(identity, "capability_digest", None)
    if current_digest is None or current_digest == plan.stack_identity:
        return
    raise CaseTransactionError(
        f"plan is bound to stack {plan.stack_identity!r} but the composed "
        f"stack is now {current_digest!r}; rebuild the plan against the "
        f"current stack before committing it"
    )


# --------------------------------------------------------------------------
# The commit executor
# --------------------------------------------------------------------------


def commit_case_write(
    plan: CaseWritePlan,
    *,
    driver_context: Any,
    transaction_id: str | None = None,
    case_lease_held: bool = False,
) -> CaseWriteRecord:
    """Commit a reviewed plan, or replay a completed one by id.

    A failed commit is rolled back; if the rollback itself fails the journal
    is kept and the error names every path left unrestored.

    The case lease is host-local and not reentrant, so a caller that already
    holds it (``--apply`` holds it for the whole step) passes
    ``case_lease_held=True``; the claim is verified, and this call then
    neither acquires nor releases a lease.
    """
    case_root = Path(plan.request.case_root)

    if transaction_id is not None:
        completed = _read_completed(case_root, transaction_id)
        if completed is not None:
            if completed.get("plan_digest") != plan.plan_digest:
                raise CaseTransactionError(
                    f"transaction {transaction_id!r} already completed against "
                    f"plan digest {completed.get('plan_digest')!r}, which does "
                    f"not match this plan's {plan.plan_digest!r}; a transaction "
                    f"id identifies one plan, and replaying it against a "
                    f"different one would silently change what already happened"
                )
            return _record_from_completed(completed)

    _check_stack_freshness(plan, driver_context)

    lease_context = None
    if case_lease_held:
        if not case_lease_is_held(case_root):
            raise CaseTransactionError(
                f"commit_case_write was called with case_lease_held=True for "
                f"{case_root}, but this thread does not hold that case's "
                f"lease; refusing to proceed unprotected rather than trust "
                f"an unverified claim"
            )
    else:
        try:
            lease_context = acquire_case_lease(case_root)
            lease_context.__enter__()
        except AttemptLeaseError as exc:
            # Report the cause the lease gives (a missing case root, say), not an assumed held lease.
            raise CaseTransactionError(
                f"cannot acquire the write lease for case {case_root}: {exc}"
            ) from exc

    try:
        pending = pending_transaction(case_root)
        if pending:
            raise CaseTransactionError(
                f"case {case_root} has an unrecovered transaction "
                f"{pending.get('transaction_id')!r}; call "
                f"recover_case_transaction() before committing another"
            )

        targets = {
            rendered.path: _resolve_target(case_root, rendered.path)
            for rendered in plan.files
        }
        _check_render_exists_before(plan.files, targets)

        tx_id = transaction_id or str(uuid.uuid4())
        before_images = [
            _before_image(rendered, targets[rendered.path]) for rendered in plan.files
        ]
        created_dirs = _all_missing_ancestors(
            case_root, [targets[rendered.path] for rendered in plan.files]
        )
        journal: dict[str, Any] = {
            "schema_version": _JOURNAL_SCHEMA_VERSION,
            "transaction_id": tx_id,
            "plan_id": plan.plan_id,
            "plan_digest": plan.plan_digest,
            "state": "preparing",
            "before_images": before_images,
            "created_dirs": created_dirs,
        }
        _write_journal(case_root, journal)

        committed: list[dict[str, Any]] = []
        try:
            journal = {**journal, "state": "applying"}
            _write_journal(case_root, journal)
            for rendered in plan.files:
                committed.append(_write_one(targets[rendered.path], rendered))
        except Exception as exc:
            _rollback(case_root, journal)
            raise CaseTransactionError(
                f"commit of {case_root} failed; rolled back: {exc}"
            ) from exc

        _remove_journal(case_root)
        record = CaseWriteRecord(
            transaction_id=tx_id,
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            committed=tuple(committed),
            evidence=(),
            status="committed",
            parameters=tuple(
                parameter.to_json() for parameter in plan.request.parameters
            ),
            expected_effects=plan.expected_effects,
        )
        _persist_completed(case_root, record)
        return record
    finally:
        if lease_context is not None:
            lease_context.__exit__(None, None, None)


def recover_case_transaction(case_root: Path) -> CaseWriteRecord | None:
    """Recover this case's pending transaction, if it has one.

    Restores every before-image and removes the journal. Returns ``None``
    when there is nothing to recover -- that is success, not "nothing
    happened to check": a case with no journal has no unrecovered
    transaction by definition.
    """
    case_root = Path(case_root)
    try:
        lease_context = acquire_case_lease(case_root)
        lease_context.__enter__()
    except AttemptLeaseError as exc:
        raise CaseTransactionError(
            f"cannot acquire the write lease to recover case {case_root}: {exc}"
        ) from exc
    try:
        journal = pending_transaction(case_root)
        if journal is None:
            return None
        _rollback(case_root, journal)
        return CaseWriteRecord(
            transaction_id=journal.get("transaction_id", "unknown"),
            plan_id=journal.get("plan_id", ""),
            plan_digest=journal.get("plan_digest", ""),
            committed=(),
            evidence=(),
            status="rolled_back",
        )
    finally:
        lease_context.__exit__(None, None, None)
