import os
from pathlib import Path

from ..tutorial_records import TutorialRecordError


#: The one environment tier of :func:`resolve_scratch_root`.
SCRATCH_ENV_VAR = "OMNIDRIVER_SCRATCH_DIR"


class ScratchRootNotSupplied(TutorialRecordError):
    """An operation that stages needs a scratch root and none was supplied.

    A ``TutorialRecordError`` so the CLI's existing refusal handlers print it
    as structured JSON, never a traceback."""


class ScratchRootInsideCasesRoot(TutorialRecordError):
    """A supplied scratch root lies inside the cases root being planned, so
    staging there would write the native tree."""


def resolve_scratch_root(
    supplied: str | Path | None, *, cases_root: str | Path | None = None,
) -> Path:
    """Where disposable working data goes: supplied, never invented.

    ``supplied`` (``--scratch-dir``, or the ``scratch_root`` keyword of a core
    entry point) > ``OMNIDRIVER_SCRATCH_DIR`` > :class:`ScratchRootNotSupplied`.
    Call it only once an operation actually stages (CLAUDE.md, "evaluate
    defaults lazily"): describing, or a sweep given ``--output-dir``, must
    never refuse for want of a scratch root it does not use.

    When ``cases_root`` is given, a scratch root at or inside it is refused
    (:class:`ScratchRootInsideCasesRoot`, naming both): staging there would
    write the native tree.
    """
    if supplied is not None and str(supplied) != "":
        root = Path(supplied).expanduser()
    elif os.environ.get(SCRATCH_ENV_VAR):
        root = Path(os.environ[SCRATCH_ENV_VAR]).expanduser()
    else:
        raise ScratchRootNotSupplied(
            "no scratch root was supplied, and this operation stages a case: pass "
            f"--scratch-dir <dir> (or set {SCRATCH_ENV_VAR}) naming a writable "
            "directory outside the cases root. There is no default; a native "
            "tutorials tree is never written (future/ENVIRONMENT_CONTRACT.md §12)"
        )
    if cases_root is not None:
        cases = Path(cases_root).expanduser()
        if root.resolve().is_relative_to(cases.resolve()):
            raise ScratchRootInsideCasesRoot(
                f"scratch root {root} is inside cases root {cases}: staging there "
                "would write the native tree; supply a --scratch-dir outside it"
            )
    return root


def default_sweep_output_dir(
    spec_path: str | Path, *, scratch_root: str | Path | None,
) -> Path:
    """Return the standard output location for a sweep specification:
    ``<scratch root>/sweeps/<spec stem>``, the scratch root resolved by
    :func:`resolve_scratch_root` (so it refuses when none is supplied). Call
    it only when no ``--output-dir`` was given."""
    return resolve_scratch_root(scratch_root) / "sweeps" / Path(spec_path).stem
