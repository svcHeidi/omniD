"""Commit a reviewed plan's bytes: every file replaced atomically, and the commit undone when a write or ``verify`` refuses.

The only module that writes a framework-authored case input; it moves bytes and knows no dictionary syntax.
A case is a scratch copy a plan re-stages whole, so a commit a kill cut short is not journaled: a marker
file beside the case's inputs says an edit began and did not end, and the next run of that case is refused
until a plan restages it. Not guaranteed: several files becoming visible together to an outside reader, or control over
writers outside the framework. A symlinked write target is refused outright.
"""

from __future__ import annotations

import json
import signal
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .case_write import CaseWritePlan, CaseWriteRecord, RenderedFile, _digest_bytes
from .runtime.attempt_lease import AttemptLeaseError, acquire_case_lease, case_lease_is_held
from .runtime.transaction_mechanics import atomic_write_bytes, fsync_directory


#: Written before the first file is replaced and removed once the commit ends or is fully rolled back;
#: one that remains means an edit of the case was cut short.
COMMIT_MARKER_FILENAME = ".omnidriver-commit"


class CaseTransactionError(RuntimeError):
    """A commit was refused, or its rollback could not be completed."""


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


def _before_image(rendered: RenderedFile, target: Path) -> tuple[bytes, int] | None:
    """The file's bytes and mode, or ``None`` when the commit creates it; refused when the file is not the one that was rendered against."""
    if not target.exists() or target.is_dir():
        return None
    try:
        content, mode = target.read_bytes(), target.stat().st_mode & 0o7777
    except OSError as exc:
        raise CaseTransactionError(
            f"cannot read {rendered.path!r} to keep its before-image "
            f"before overwriting it: {exc}"
        ) from exc
    if _digest_bytes(content) != rendered.before_digest:
        raise CaseTransactionError(
            f"{rendered.path!r} changed since it was rendered (its digest is no longer "
            f"{rendered.before_digest!r}); plan again rather than overwrite an edit nobody reviewed"
        )
    return content, mode


def _missing_ancestors(case_root: Path, targets: list[Path]) -> list[Path]:
    """Directories the commit will create, deepest first, so a rollback removes only those."""
    created: set[Path] = set()
    for target in targets:
        current = target.parent
        while current != case_root and not current.exists():
            created.add(current)
            current = current.parent
    return sorted(created, key=lambda path: len(path.parts), reverse=True)


@contextmanager
def _signals_deferred() -> Iterator[None]:
    """Hold SIGINT and SIGTERM until the block ends, so a second signal cannot cut a rollback short."""
    if not hasattr(signal, "pthread_sigmask"):
        yield
        return
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _rollback(
    case_root: Path, reached: list[Path], before: Mapping[Path, tuple[bytes, int] | None], created_dirs: list[Path],
) -> None:
    """Put every file the commit reached back as it was; on any failure raise naming every path left unrestored."""
    failures: list[tuple[Path, Exception]] = []
    for target in reached:
        image = before[target]
        try:
            if image is None:
                target.unlink(missing_ok=True)
                if target.parent.exists():
                    fsync_directory(target.parent)
            else:
                atomic_write_bytes(target, image[0], mode=image[1])
        except Exception as exc:  # noqa: BLE001 - collected, not swallowed
            failures.append((target, exc))
    if failures:
        detail = "; ".join(f"{path}: {exc}" for path, exc in failures)
        raise CaseTransactionError(
            f"rollback failed restoring {[str(path) for path, _ in failures]}; the case "
            f"{case_root} is left half-written, so plan again to restage it: {detail}"
        )
    for directory in created_dirs:
        try:
            directory.rmdir()
        except OSError:
            # Not empty (something else legitimately lives there) or already gone.
            pass


def interrupted_commit(case_root: Path) -> tuple[str, ...] | None:
    """The paths of an edit this case's commit marker says was cut short, or ``None`` when there is none."""
    marker = Path(case_root) / COMMIT_MARKER_FILENAME
    if not marker.exists():
        return None
    try:
        return tuple(json.loads(marker.read_text())["paths"])
    except (OSError, ValueError, KeyError, TypeError):
        return ()


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


def commit_case_write(
    plan: CaseWritePlan,
    *,
    driver_context: Any,
    case_lease_held: bool = False,
    verify: Callable[[], None] | None = None,
) -> CaseWriteRecord:
    """Commit a reviewed plan.

    A failed write rolls the commit back. ``verify`` runs once every file is
    written: what it raises rolls the commit back and propagates unchanged.
    If the rollback itself fails, the error names every path left unrestored;
    when a signal's ``KeyboardInterrupt`` or ``SystemExit`` caused the commit
    to stop, that stays what propagates and the failure is told beside it.
    A signal that arrives during the rollback is held until it ends.

    The case lease is host-local and not reentrant, so a caller that already
    holds it (``--apply`` holds it for the whole step) passes
    ``case_lease_held=True``; the claim is verified, and this call then
    neither acquires nor releases a lease.
    """
    case_root = Path(plan.request.case_root)
    _check_stack_freshness(plan, driver_context)

    with ExitStack() as owned:
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
                owned.enter_context(acquire_case_lease(case_root))
            except AttemptLeaseError as exc:
                # Report the cause the lease gives (a missing case root, say), not an assumed held lease.
                raise CaseTransactionError(
                    f"cannot acquire the write lease for case {case_root}: {exc}"
                ) from exc

        targets = {rendered.path: _resolve_target(case_root, rendered.path) for rendered in plan.files}
        _check_render_exists_before(plan.files, targets)
        before = {targets[rendered.path]: _before_image(rendered, targets[rendered.path]) for rendered in plan.files}
        created_dirs = _missing_ancestors(case_root, list(before))

        marker = case_root / COMMIT_MARKER_FILENAME
        reached: list[Path] = []
        try:
            atomic_write_bytes(marker, json.dumps({"paths": [rendered.path for rendered in plan.files]}).encode())
            try:
                for rendered in plan.files:
                    reached.append(targets[rendered.path])
                    atomic_write_bytes(targets[rendered.path], rendered.content, mode=rendered.mode)
            except Exception as exc:
                raise CaseTransactionError(f"commit of {case_root} failed: {exc}") from exc
            if verify is not None:
                verify()
        except BaseException as error:
            with _signals_deferred():
                try:
                    _rollback(case_root, reached, before, created_dirs)
                except CaseTransactionError as failure:
                    if isinstance(error, Exception):
                        raise
                    # A signal's own exit stays what the caller sees; the failed rollback is told beside it.
                    error.add_note(str(failure))
                    print(failure, file=sys.stderr)
                else:
                    marker.unlink(missing_ok=True)
            raise
        marker.unlink(missing_ok=True)

    return CaseWriteRecord(
        committed=tuple(rendered.path for rendered in plan.files),
        parameters=plan.request.parameters,
        expected_effects=plan.expected_effects,
    )
