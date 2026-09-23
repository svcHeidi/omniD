"""Commit a reviewed plan's bytes, recoverably.

What this guarantees:

* Each file is replaced atomically, so a framework reader never observes a
  partially written file.
* A journal records every before-image before any write, so an interrupted
  transaction is recoverable and a failed one is rolled back: overwritten
  files are restored, created files are removed, and directories created only
  for the transaction are removed.
* A case lease serializes this framework's attempts against one case.

What this does NOT guarantee, and must not be documented as guaranteeing
(proposal defect W2):

* Simultaneous atomic visibility of several files to an arbitrary outside
  process. A process reading the case during a multi-file commit can observe
  a mixed state. The supported reader model is: this framework's own
  readers, and outside readers that read after the transaction completes.
* Control over writers outside the framework. A lease coordinates this
  framework's attempts. A user editing a dictionary in an editor is not
  prevented -- an edit that changes the file's content in place is detected
  at precondition recheck as drift, which refuses the commit. A read
  dependency replaced by a *symlink* is a different case and is refused
  outright rather than detected as drift by digest (R3 finding 4, corrected
  2026-09-23): dereferencing it would validate one file's identity while
  reading another's content, so :func:`_check_preconditions` refuses to trust
  a symlinked precondition target at all, the same way :func:`_resolve_target`
  already refused a symlinked write target.
* Durability beyond what ``fsync`` on the file and its directory provides on
  the host filesystem. Network filesystems that reorder or defer writes are
  outside the supported profile -- this module has been exercised only
  against a local POSIX filesystem, and that is what these guarantees are
  claims about, not POSIX in general.

This is the only module in the repository that writes a framework-authored
case input, once G3 closes. It moves bytes and digests; it does not know what
a ``;`` means. If a caller needs dictionary syntax, the caller's format owner
renders it into a :class:`~omnidriver.core.case_write.RenderedFile` first.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from .case_write import (
    CaseWritePlan,
    CaseWriteRecord,
    RenderedFile,
    _digest_bytes,
)
from .planning_types import SimulationAuditItem
from .runtime.attempt_lease import AttemptLeaseError, acquire_case_lease
from .runtime.remediation_transaction import _atomic_write_bytes, _fsync_directory

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
#: temp-directory record, for the same reason the remediation journal and the
#: case lease both live case-adjacent: recovery must find this from the case
#: alone, with nothing else supplied.
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
    path = _journal_path(case_root)
    payload = (json.dumps(dict(transaction), sort_keys=True, indent=2) + "\n").encode()
    _atomic_write_bytes(path, payload)
    _fsync_directory(path.parent)


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
    # R3 finding 5 (2026-09-23): `TRANSACTION_STATES` was declared but never
    # checked -- any `state` value was accepted. Rollback is unconditional on
    # this field today, so an unrecognised state was not silently treated as
    # "nothing to recover"; but the invariant was dead, and a corrupted or
    # hand-edited journal with a bogus state would have been read as though
    # it were legitimate. Matches
    # `remediation_transaction.read_remediation_transaction`'s own
    # status-validation pattern.
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
    path = _completed_path(case_root, record.transaction_id)
    payload = (json.dumps(record.to_json(), sort_keys=True, indent=2) + "\n").encode()
    _atomic_write_bytes(path, payload)
    _fsync_directory(path.parent)


def _record_from_completed(payload: Mapping[str, Any]) -> CaseWriteRecord:
    return CaseWriteRecord(
        transaction_id=payload["transaction_id"],
        plan_id=payload["plan_id"],
        plan_digest=payload["plan_digest"],
        committed=tuple(payload.get("committed", ())),
        evidence=tuple(payload.get("evidence", ())),
        status=payload.get("status", "committed"),
    )


# --------------------------------------------------------------------------
# Precondition rechecking
# --------------------------------------------------------------------------


def _check_environment_precondition(
    precondition: "Precondition", environment: Mapping[str, str],
) -> None:
    """Recheck one ``environment`` precondition against the environment the
    commit is running under (R3 finding 3, 2026-09-23).

    Recorded at planning time as either a value (``digest`` is that value's
    digest, ``must_be_absent`` is ``False``) or an absence (``digest`` is
    ``None``, ``must_be_absent`` is ``True``) -- there is no third state, so
    an absent variable that later appears is exactly as much a change as a
    present one whose value changed (the same "absence is a dependency"
    principle audit finding F2 established for include candidates).
    """
    key = precondition.target
    value = environment.get(key)
    if precondition.must_be_absent:
        if value is not None:
            raise CaseTransactionError(
                f"precondition on environment variable {key!r} expected it "
                f"to be unset, but it is now {value!r}; the plan was made "
                f"assuming this variable played no part in resolution"
            )
        return
    if value is None:
        raise CaseTransactionError(
            f"precondition on environment variable {key!r} expected a value "
            f"but it is now unset; the case changed since the plan was made"
        )
    actual = _digest_bytes(value.encode())
    if actual != precondition.digest:
        raise CaseTransactionError(
            f"precondition on environment variable {key!r} failed: its "
            f"value changed since the plan was made"
        )


def _check_preconditions(
    case_root: Path, preconditions: tuple, *, environment: Mapping[str, str],
) -> None:
    """Recheck every precondition against the filesystem, before any write.

    ``file`` and ``include`` are checked identically -- both name a
    case-relative path whose content must still match a digest; the
    distinction between them is provenance (why the plan cared), not
    mechanics. ``source_artifact`` is checked the same generic way: no case
    in this batch exercises one whose target is not a case-relative file, and
    a target that does not resolve to one simply reads as "missing" and
    refuses -- fail-closed, not silently accepted. ``environment`` is checked
    against ``environment`` (the execution environment the commit runs
    under, or ``os.environ`` when the caller supplied none), never the
    filesystem -- implemented 2026-09-23 (R3 finding 3); see
    :func:`_check_environment_precondition`.

    A symlink at a ``file``/``include``/``source_artifact``/``absence``
    target is refused outright, mirroring :func:`_resolve_target`'s refusal
    of a symlink write target (R3 finding 4, 2026-09-23): dereferencing it
    would validate one file's identity while reading another's content,
    which is exactly how a case-relative read dependency could be quietly
    replaced by a symlink to content outside the case with its precondition
    still reporting green.
    """
    for precondition in preconditions:
        if precondition.kind == "environment":
            _check_environment_precondition(precondition, environment)
            continue
        target = Path(case_root) / precondition.target
        is_symlink = target.is_symlink()
        exists = target.is_file()
        if precondition.must_be_absent:
            if exists or is_symlink:
                raise CaseTransactionError(
                    f"precondition on {precondition.target!r} requires it to be "
                    f"absent, but it exists"
                )
            continue
        if is_symlink:
            raise CaseTransactionError(
                f"precondition on {precondition.target!r} targets a symlink; "
                f"refusing to trust it as {precondition.kind!r} evidence -- a "
                f"symlink can point to different content than what was "
                f"digested when the plan was made"
            )
        if not exists:
            raise CaseTransactionError(
                f"precondition on {precondition.target!r} expected digest "
                f"{precondition.digest!r}, but the target is missing"
            )
        # R3 blocker 1 (2026-09-23): this read used to be unguarded. A target
        # with no read permission (``mode=0o000`` is a plan-legal
        # ``RenderedFile.mode``, so this is reachable by ordinary use, not a
        # contrived edge case) raised a bare ``PermissionError`` here, which
        # propagated straight out of ``commit_case_write`` past every
        # caller's and every test's assumption that a commit failure
        # surfaces as ``CaseTransactionError``.
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise CaseTransactionError(
                f"cannot read {precondition.target!r} to check its "
                f"precondition: {exc}"
            ) from exc
        actual = _digest_bytes(content)
        if actual != precondition.digest:
            raise CaseTransactionError(
                f"precondition on {precondition.target!r} failed: expected "
                f"digest {precondition.digest!r}, found {actual!r}; the case "
                f"changed since the plan was made"
            )


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------


def _resolve_target(case_root: Path, rendered_path: str) -> Path:
    """The path to write, after refusing a symlink escape.

    ``RenderedFile`` already refused an absolute or ``..``-bearing spelling at
    construction. This checks the same thing against the resolved real path,
    because a symlink can move a legal spelling outside the case between
    planning and commit.
    """
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
    """What ``target`` looked like before this transaction touches it.

    R3 blocker 1 (2026-09-23): this read used to be unguarded, with the same
    unwrapped-``PermissionError`` failure mode as ``_check_preconditions``'s
    own read (see its matching comment). Any ``OSError`` reading the
    before-image is now reported as a ``CaseTransactionError`` naming the
    path and the operation, with the original preserved as ``__cause__``.
    """
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
    """Put one file back the way the journal recorded it.

    Idempotent by construction: restoring a file that was never actually
    touched (because the transaction was interrupted before reaching it) just
    rewrites the same bytes, or unlinks a path that was never created. That
    is what lets recovery replay the full before-image list unconditionally
    rather than needing to know exactly how far a partial commit got.
    """
    if before_image.get("existed_before"):
        content = base64.b64decode(before_image["content_base64"])
        _atomic_write_bytes(target, content, mode=before_image.get("mode"))
        _fsync_directory(target.parent)
    else:
        target.unlink(missing_ok=True)
        if target.parent.exists():
            _fsync_directory(target.parent)


def _all_missing_ancestors(case_root: Path, targets: list) -> list:
    """Directories that exist nowhere yet, deepest first.

    Recorded once, before any write, so rollback can remove exactly the
    directories this transaction created -- and none that predate it, even
    if they end up empty for an unrelated reason.
    """
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
    """Restore every before-image the journal recorded.

    Attempts every restore rather than stopping at the first failure, so a
    caller sees the complete set of paths a failed rollback left in an
    unknown state. If any restore fails, the journal is left in place --
    recorded, not silently dropped -- and this raises rather than reporting a
    clean rollback that did not happen.
    """
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
    """Refuse a plan bound to a stack that is no longer the composed one.

    Best-effort: applies only when ``driver_context`` actually carries a
    :class:`~omnidriver.core.provider_identity.StackIdentity` (its public
    ``identity`` field -- never ``driver_context.providers`` directly, which
    no production module may touch). A bare stand-in, as this module's own
    unit tests deliberately pass, has no such attribute and this check is a
    no-op for it; those tests are exercising journal and rollback mechanics,
    not stack binding.

    Known limit, not fixed here (audit finding C4): most capabilities
    contribute a placeholder digest to ``capability_digest``, so an edited
    implementation in an editable install with no version bump is invisible
    to this check. It catches a changed provider set, version, profile,
    dictionary vocabulary or manifest -- not an edited renderer's content.
    """
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
    execution_env: Any,
    transaction_id: str | None = None,
) -> CaseWriteRecord:
    """Commit a reviewed plan, or replay a completed one by id.

    Ordering (roadmap lifecycle steps 5-6): replay check -> stack-freshness
    check -> lease -> unrecovered-journal check -> preconditions -> path
    safety -> journal -> writes -> (rollback on failure | completion record).
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

    try:
        lease_context = acquire_case_lease(case_root)
        lease_context.__enter__()
    except AttemptLeaseError as exc:
        raise CaseTransactionError(
            f"case {case_root} write lease is already held: {exc}"
        ) from exc

    try:
        pending = pending_transaction(case_root)
        if pending:
            raise CaseTransactionError(
                f"case {case_root} has an unrecovered transaction "
                f"{pending.get('transaction_id')!r}; call "
                f"recover_case_transaction() before committing another"
            )

        environment = execution_env if execution_env is not None else os.environ
        _check_preconditions(case_root, plan.preconditions, environment=environment)

        targets = {
            rendered.path: _resolve_target(case_root, rendered.path)
            for rendered in plan.files
        }

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
        )
        _persist_completed(case_root, record)
        return record
    finally:
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
            f"cannot recover case {case_root}: write lease is already held: {exc}"
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


def unrecovered_transaction_audit(case_root: Path) -> SimulationAuditItem | None:
    """A ``case_inputs`` coverage item when this case has an unrecovered transaction.

    Reuses the existing coverage gate
    (:class:`~omnidriver.core.planning_types.SimulationAuditItem` plus
    :func:`~omnidriver.core.runtime.launch_readiness.is_launchable`) rather
    than inventing a second one, per this plan's instruction for Task 6. A
    case whose last transaction was interrupted has inputs nobody can vouch
    for until :func:`recover_case_transaction` runs; a caller that folds this
    item into its ``simulation_audit`` tuple makes ``is_launchable`` refuse to
    launch against that case.

    **Not wired into any dispatch call site by this batch.** Populating a
    real entry's ``simulation_audit`` with a ``case_inputs`` stage is Tasks
    8/9's vertical-slice work -- this function only proves the seam behaves,
    from this module's own tests. Calling it is what would make ``unavailable``
    reach a real run; nothing in Tasks 5-7 calls it from a dispatch path.
    """
    pending = pending_transaction(case_root)
    if not pending:
        return None
    return SimulationAuditItem(
        stage="case_inputs",
        status="unavailable",
        points=0,
        max_points=0,
        summary=(
            f"case {case_root} has an unrecovered write transaction "
            f"{pending.get('transaction_id', 'unknown')!r}; its inputs are "
            f"not known until recover_case_transaction() runs"
        ),
        evidence={"transaction_id": pending.get("transaction_id")},
    )
