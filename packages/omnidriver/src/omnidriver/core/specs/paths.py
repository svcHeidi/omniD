import os
from pathlib import Path

from ..tutorial_records import TutorialRecordError


def repo_root_default() -> Path:
    """Locate the repository root using a three-tier fallback.

    Every tier walks up from this file and recognises its target by marker
    files/directories, never by counting path segments — a fixed
    ``parents[N]`` silently breaks the moment this file's nesting depth
    changes (it did, twice, across the package split), and breaks silently
    because every candidate directory exists, it's just the wrong one.

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


# No tutorials_root_default() here any more. It returned repo_root_default() /
# "tutorials", so core invented a location for a caller's cases and raised
# outside a checkout -- which is why core could not plan a case from an
# installed wheel. A base is supplied now; see future/ENVIRONMENT_CONTRACT.md
# §12 on supplied-versus-discovered.


def repo_root_or_none() -> Path | None:
    """The repository root, or ``None`` when there is no checkout.

    ``repo_root_default()`` raises rather than guessing, which is right when a
    caller genuinely needs the repository. A caller asking "am I inside a
    checkout at all?" wants an answer, not an exception -- and gets ``None``
    from an installed wheel, where the honest answer is "no".
    """
    try:
        return repo_root_default()
    except RuntimeError:
        return None


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
    (:class:`ScratchRootInsideCasesRoot`, naming both) -- the rule
    ``ConformanceTarget`` already enforced.

    Replaced ``scratch_root(base)`` on 2026-09-26 (owner decision). That
    defaulted to ``<base>/.omnidriver`` and its callers passed ``cases_root``,
    so planning a tutorial record wrote ``.omnidriver/`` into the native tree
    and failed with ``PermissionError`` on a read-only install (openCARP's
    ``/usr/local/lib/opencarp/share/tutorials``). A scratch location has no
    ambient truth, so defaulting one invents it
    (future/ENVIRONMENT_CONTRACT.md §12). Renamed rather than re-signed so a
    stale ``scratch_root(cases_root)`` call fails to import instead of
    silently treating the cases root as a supplied scratch root.
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


def default_setup_dir_name(case_dir_name: str) -> str:
    normalized_case_dir = case_dir_name.strip()
    if not normalized_case_dir:
        raise ValueError("case_dir_name cannot be empty")
    case_leaf = Path(normalized_case_dir).name
    return f"setup{case_leaf[:1].upper()}{case_leaf[1:]}"


def resolve_spec_paths(
    *,
    cases_root: Path | None,
    case_dir_name: str,
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = None,
    default_output_dir_name: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    # No ambient default: a caller who names no base gets the working
    # directory, not a location core invented for them.
    resolved_cases_root = (
        Path(cases_root) if cases_root is not None else Path.cwd()
    )
    resolved_case_dir = case_dir_name.strip()
    if not resolved_case_dir:
        raise ValueError("case_dir_name cannot be empty")
    resolved_setup_dir = setup_dir_name or default_setup_dir_name(resolved_case_dir)
    resolved_output_dir = output_dir_name or default_output_dir_name
    if resolved_output_dir is None:
        raise ValueError("output_dir_name or default_output_dir_name must be provided")

    case_root = resolved_cases_root / resolved_case_dir
    setup_root = case_root / resolved_setup_dir
    output_dir_path = Path(resolved_output_dir)
    # A caller that has already isolated this case at case_root (staged
    # sweep cases; see sweep_runner._materialize_entry_case) has nothing
    # left for output_dir_name to distinguish, and passes "." to say so
    # explicitly. Collapse to case_root itself rather than case_root/".":
    # OpenFOAM's own convention is that postProcessing/, constant/, system/,
    # 0/ all sit directly under the case directory -- there is exactly one
    # real location a solve writes into, and output_dir must name that one
    # location, not a second path nothing ever populates. Confirmed
    # directly: a real cardiacFoam solve wrote postProcessing/ under
    # case_root, while the workflow's own artifact check looked for it
    # under case_root/case_root's-own-output-dir-name and reported the
    # (present, correct) artifacts as missing.
    output_dir = (
        case_root
        if output_dir_path == Path(".")
        else case_root / output_dir_path
    )
    return case_root, setup_root, output_dir


def resolve_run_script_path(
    *,
    cases_root: Path | None,
    run_script_relpath: Path,
) -> Path:
    if run_script_relpath.is_absolute():
        return run_script_relpath

    # A relative run-script path is relative to the workspace, not to a
    # repository that may not exist. Both repo-root lookups are gone: they were
    # appended EAGERLY, so this raised from a wheel install even when
    # cases_root had been supplied and the script existed under it -- the
    # candidate list was built before the loop that would have found it.
    candidate_roots: list[Path] = []
    if cases_root is not None:
        candidate_roots.append(Path(cases_root))
    candidate_roots.append(Path.cwd())

    checked_paths: list[Path] = []
    seen: set[Path] = set()
    for root in candidate_roots:
        resolved_root = root.resolve()
        if resolved_root in seen:
            continue
        seen.add(resolved_root)
        candidate = resolved_root / run_script_relpath
        checked_paths.append(candidate)
        if candidate.exists():
            return candidate

    checked_str = ", ".join(str(path) for path in checked_paths)
    raise FileNotFoundError(
        f"Run script not found for '{run_script_relpath}'. Checked: {checked_str}. "
        "Use an absolute path or a path relative to repository root."
    )
