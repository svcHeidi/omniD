import os
from pathlib import Path


def cardiacfoam_monorepo_root(start: Path | None = None) -> Path | None:
    """Walk parent directories looking for the full cardiacFoam monorepo root.

    Returns the first ancestor of ``start`` (default: this file) that has
    both ``tutorials/`` and ``applications/`` siblings -- the monorepo
    ``omnidriver`` was extracted from -- or ``None`` when running in a
    standalone checkout that doesn't happen to sit inside that tree (the
    normal case: this repo has its own remote and isn't nested in the
    monorepo). Shared by each package's test ``conftest.py`` (via
    ``skip_without_monorepo``) and by the root-level ``scripts/`` (e.g.
    ``regenerate-ionic-catalog.py``, ``scan-dict-keys.py``) that read
    monorepo-only content. No call sites exist inside core itself; this
    function has no callers unless something outside core imports it.
    """
    current = (start or Path(__file__)).resolve()
    for parent in current.parents:
        if (parent / "tutorials").exists() and (parent / "applications").exists():
            return parent
    return None


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
        ``tutorials/`` sibling but no ``src/`` — driverFOAM cloned with a
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


def scratch_root(base: Path) -> Path:
    """Disposable working data, kept beside the workspace rather than inside
    the installation.

    ``OMNIDRIVER_SCRATCH_DIR`` overrides. Deliberately NOT the OS temp
    directory: sweep outputs default under here, and somewhere the OS reaps
    would be worse than the repository-local ``.tmp/driverfoam`` this replaces
    -- which was both solver-branded and unwritable on a read-only install.
    """
    override = os.environ.get("OMNIDRIVER_SCRATCH_DIR")
    if override:
        return Path(override).expanduser()
    return Path(base) / ".omnidriver"


def default_sweep_output_dir(spec_path: str | Path, *, base: Path) -> Path:
    """Return the standard output location for a sweep specification."""
    return scratch_root(base) / "sweeps" / Path(spec_path).stem


def default_setup_dir_name(case_dir_name: str) -> str:
    normalized_case_dir = case_dir_name.strip()
    if not normalized_case_dir:
        raise ValueError("case_dir_name cannot be empty")
    case_leaf = Path(normalized_case_dir).name
    return f"setup{case_leaf[:1].upper()}{case_leaf[1:]}"


def resolve_spec_paths(
    *,
    tutorials_root: Path | None,
    case_dir_name: str,
    setup_dir_name: str | None = None,
    output_dir_name: str | Path | None = None,
    default_output_dir_name: str | Path | None = None,
) -> tuple[Path, Path, Path]:
    # No ambient default: a caller who names no base gets the working
    # directory, not a location core invented for them.
    resolved_tutorials_root = (
        Path(tutorials_root) if tutorials_root is not None else Path.cwd()
    )
    resolved_case_dir = case_dir_name.strip()
    if not resolved_case_dir:
        raise ValueError("case_dir_name cannot be empty")
    resolved_setup_dir = setup_dir_name or default_setup_dir_name(resolved_case_dir)
    resolved_output_dir = output_dir_name or default_output_dir_name
    if resolved_output_dir is None:
        raise ValueError("output_dir_name or default_output_dir_name must be provided")

    case_root = resolved_tutorials_root / resolved_case_dir
    setup_root = case_root / resolved_setup_dir
    output_dir = case_root / Path(resolved_output_dir)
    return case_root, setup_root, output_dir


def resolve_run_script_path(
    *,
    tutorials_root: Path | None,
    run_script_relpath: Path,
) -> Path:
    if run_script_relpath.is_absolute():
        return run_script_relpath

    # A relative run-script path is relative to the workspace, not to a
    # repository that may not exist. Both repo-root lookups are gone: they were
    # appended EAGERLY, so this raised from a wheel install even when
    # tutorials_root had been supplied and the script existed under it -- the
    # candidate list was built before the loop that would have found it.
    candidate_roots: list[Path] = []
    if tutorials_root is not None:
        candidate_roots.append(Path(tutorials_root))
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
