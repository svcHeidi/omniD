import os
from pathlib import Path

from ..tutorial_records import TutorialRecordError


def repo_root_default() -> Path:
    """Locate the repository root using a three-tier fallback.

    Every tier walks up from this file and recognises its target by marker
    files/directories, never by counting path segments — a fixed
    ``parents[N]`` breaks silently the moment this file's nesting depth
    changes, because every candidate directory exists, just the wrong one.

    Tier 1 (monorepo): ancestor directory that has both ``tutorials/`` and
        ``src/`` siblings — the full cardiacFoam checkout.
    Tier 2 (standalone-with-tutorials): ancestor directory that has a
        ``tutorials/`` sibling but no ``src/`` — omnidriver cloned with a
        companion tutorials tree.
    Tier 3 (fully standalone): the ancestor directory that has both
        ``packages/`` and ``ARCHITECTURE.md`` — the omnidriver monorepo
        root itself. This is the fallback when neither a cardiacFoam
        monorepo nor an external tutorials tree is present, e.g. in a
        temp-folder clone or CI.

    Raises ``RuntimeError`` if no tier matches, rather than returning some
    existing-but-wrong ancestor directory (e.g. a package's own ``src/``) —
    a caller silently writing scratch output or resolving tutorials against
    the wrong root is worse than a loud, early failure.
    """
    current = Path(__file__).resolve()
    tier2_candidate: Path | None = None
    for parent in current.parents:
        has_tutorials = (parent / "tutorials").exists()
        has_src = (parent / "src").exists()
        # Tier 1: full monorepo layout
        if has_tutorials and has_src:
            return parent
        # Remember first ancestor with tutorials/ only (Tier 2)
        if has_tutorials and tier2_candidate is None:
            tier2_candidate = parent
    if tier2_candidate is not None:
        return tier2_candidate
    # Tier 3: the omnidriver monorepo root, recognised by its own markers.
    for parent in current.parents:
        if (parent / "packages").is_dir() and (parent / "ARCHITECTURE.md").is_file():
            return parent
    raise RuntimeError(
        f"Could not locate the omnidriver repository root by walking up "
        f"from {current}: no ancestor has both tutorials/+src/ (monorepo), "
        f"tutorials/ alone, or packages/+ARCHITECTURE.md (standalone repo)."
    )


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
