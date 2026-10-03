"""Commit a reviewed plan's bytes, recoverably.

What this guarantees:

* Each file is replaced atomically, so a framework reader never observes a
  partially written file.
* A journal records every before-image before any write, so an interrupted
  transaction is recoverable and a failed one is **rolled back when the
  rollback itself succeeds**: overwritten files are restored, created files
  are removed, and directories created only for the transaction are removed.
  Rollback can itself fail -- see :func:`_rollback`'s own docstring. When it
  does, the journal is left in place rather than removed, and
  :func:`commit_case_write` raises naming every path restoration failed for;
  the case's prior state remains recoverable from that journal, but it is
  not restored automatically a second time.
* A case lease serializes this framework's attempts against one case.

What this does NOT guarantee, and must not be documented as guaranteeing:

* Simultaneous atomic visibility of several files to an arbitrary outside
  process. A process reading the case during a multi-file commit can observe
  a mixed state. The supported reader model is: this framework's own
  readers, and outside readers that read after the transaction completes.
* Control over writers outside the framework. A lease coordinates this
  framework's attempts. A user editing a dictionary in an editor is not
  prevented. A symlinked write target is refused outright
  (:func:`_resolve_target`).
* Durability beyond what ``fsync`` on the file and its directory provides on
  the host filesystem. Network filesystems that reorder or defer writes are
  outside the supported profile -- this module has been exercised only
  against a local POSIX filesystem, and that is what these guarantees are
  claims about, not POSIX in general.

This is the only module in the repository that writes a framework-authored
case input. It moves bytes and digests; it does not know what a ``;`` means.
If a caller needs dictionary syntax, the caller's format owner renders it
into a :class:`~omnidriver.core.case_write.RenderedFile` first.
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
        # Absent in a record persisted before these fields existed -- the
        # same "no field means the prior, only behaviour" default every
        # other `.get(...)` here already uses.
        parameters=tuple(payload.get("parameters", ())),
        expected_effects=tuple(payload.get("expected_effects", ())),
    )


def _check_render_exists_before(
    files: tuple[RenderedFile, ...], targets: Mapping[str, Path],
) -> None:
    """Refuse a rendered file whose ``exists_before`` claim contradicts the
    real filesystem, before any write.

    ``render_case_files``'s own contract (``plugin_interface.py``) says a
    renderer "reads the case ... to patch an existing file" through
    ``snapshot_root``, "an isolated copy core provides". A renderer that
    (wrongly) believed a document was brand new, when the case already held
    one with other keys in it, would produce a ``RenderedFile`` whose
    committed bytes hold ONLY the keys that renderer touched, discarding
    every sibling key the moment ``_write_one`` replaces the file. This is
    the generic, solver-agnostic guard: it does not know what a document
    means, only whether the claim about its prior existence matches disk.
    """
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

    Any ``OSError`` reading the before-image is reported as a
    ``CaseTransactionError`` naming the path and the operation, with the
    original preserved as ``__cause__`` -- the same guard
    ``_check_preconditions``'s own read needs, and for the same reason.
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

    Known limit: most contract members contribute a placeholder digest to
    ``capability_digest``, so an edited implementation in an editable
    install with no version bump is invisible to this check. It catches a
    changed provider set, version, profile, dictionary vocabulary or
    manifest -- not an edited renderer's content.
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
    transaction_id: str | None = None,
    case_lease_held: bool = False,
) -> CaseWriteRecord:
    """Commit a reviewed plan, or replay a completed one by id.

    Ordering: replay check -> stack-freshness check -> lease ->
    unrecovered-journal check -> path safety -> journal ->
    writes -> (rollback on failure | completion record).

    The lease this function acquires is host-local and **not reentrant**
    (see ``runtime.attempt_lease``'s own docstring) -- a second
    ``acquire_case_lease`` from the same thread finds its own record already
    on disk and refuses it as a conflicting owner. A caller that already
    holds the case lease for the whole operation it is part of (e.g.
    `cli.py`'s `--apply` dispatch, which holds it for the whole `step`
    execution) passes ``case_lease_held=True`` to say so; this is verified,
    not merely trusted, against `case_lease_is_held` -- a caller that lies
    about holding it is a bug worth failing loudly for, not silently running
    unprotected -- and this call then neither acquires nor releases a second
    lease, relying on the caller's own for the whole duration. Every other
    caller omits it, defaults to ``False``, and acquires its own lease as
    usual.
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
            # Report the cause `exc` actually gives (e.g. `case_root` not
            # existing at all), not an assumed "write lease is already held".
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
            # `expected_effects` is copied from the plan unchanged, alongside
            # the same validated `ParameterAssignment`s the channel wrote
            # from (`plan.request.parameters`, not a second description of
            # them).
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
        # Same as commit_case_write's: report the cause acquire_case_lease
        # actually gives.
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
