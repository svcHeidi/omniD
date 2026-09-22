"""An etc dependency must be the file the native runtime would select.

`#includeEtc "caseDicts/x"` was resolved as `$FOAM_ETC/caseDicts/x` and nothing
else. Native `findEtcFile` searches up to six locations -- user, then site,
then other/distribution, each gated by a `u`/`g`/`o` mode letter -- so an
override at any of those levels, or an explicit `FOAM_CONFIG_ETC`/
`FOAM_CONFIG_MODE`, can change which file the solver reads while the inspector
recorded a different one. Dependency closure then names a file the run did
not use, and a precondition digest over that file proves nothing about the
run.

These fixtures are directory layouts, not an OpenFOAM installation. They assert
which candidate is selected and which candidates were searched, not what
foamDictionary would print. The native comparison lives in
``tests/core/test_effective_dictionary.py``, guarded by the same ``@native``
marker as the rest of that file's runtime-backed tests, so it runs only when
an OpenFOAM installation is actually discoverable.

Corrected 2026-09-22, three times:

1. First version modelled only three locations (versioned user, versioned
   site, distribution) and built the user/site directories from
   ``WM_PROJECT_VERSION``. Measured against a real ESI v2412 install, native's
   own ``foamEtcFile -list`` names five locations -- user/site qualified by
   ``FOAM_API``, not ``WM_PROJECT_VERSION`` (they differ on ESI builds, e.g.
   ``2412`` vs ``v2412``) -- plus unversioned user and site fallbacks.
   ``test_a_wm_project_version_qualified_user_file_is_ignored...`` is the
   fixture form of that regression: the first draft's own
   ``$HOME/.OpenFOAM/v2412`` candidate is a location native never reads, so a
   file placed there was selected by the driver while the real run kept
   reading straight through to the distribution file underneath it.
2. Second version covered those five locations but not ``FOAM_CONFIG_ETC``
   (an explicit override, searched immediately before the distribution
   file) or ``FOAM_CONFIG_MODE`` (restricts the search to a subset of
   user/group/other). An independent review reproduced both live:
   ``FOAM_CONFIG_ETC`` set with nothing else shadowing it selected the
   override natively while this function still selected the distribution
   file; ``FOAM_CONFIG_MODE=o`` with a user file present had native
   deliberately skip user/group entirely while this function still selected
   the user file. ``test_foam_config_mode_o_excludes_user_and_group_entirely``
   is that second regression's fixture form.
3. Same review: the Foundation (openfoam.org) branch modelled the site
   default from ``WM_PROJECT_DIR`` -- correct for ESI, but Foundation's own
   published source defaults the site root from the *parent* of the versioned
   install (``WM_PROJECT_INST_DIR``), not from ``WM_PROJECT_DIR`` itself.
   ``_foundation_environment`` below pinned ``WM_PROJECT_SITE`` explicitly, so
   it never actually exercised either family's *default*,
   ``test_foundation_style_site_root_defaults_from_wm_project_inst_dir`` does.
   Foundation is verified against its **published source only**
   (``raw.githubusercontent.com/OpenFOAM/OpenFOAM-dev/master/{bin/foamEtcFile,
   etc/bashrc}``, fetched 2026-09-22) -- no Foundation installation exists on
   this machine, so this family has no live comparison the way ESI does in
   ``test_effective_dictionary.py``. That gap is recorded, not guessed away.
"""

from pathlib import Path

from omnidriver.openfoam.effective_dictionary import find_etc_file


def _layout(tmp_path: Path) -> dict[str, Path]:
    """The candidate directories, named after `foamEtcFile`'s own `dirList`
    construction (`userDir`, `groupDir`/`siteDir`, `projectDir`), plus a
    `config_etc` directory for the `FOAM_CONFIG_ETC` override."""
    user_versioned = tmp_path / "home" / ".OpenFOAM" / "2412"
    user_unversioned = tmp_path / "home" / ".OpenFOAM"
    site_versioned = tmp_path / "site" / "2412" / "etc"
    site_unversioned = tmp_path / "site" / "etc"
    dist = tmp_path / "opt" / "openfoam2412" / "etc"
    config_etc = tmp_path / "config_etc_override"
    for directory in (
        user_versioned, user_unversioned, site_versioned, site_unversioned,
        dist, config_etc,
    ):
        (directory / "caseDicts").mkdir(parents=True, exist_ok=True)
    return {
        "user_versioned": user_versioned,
        "user_unversioned": user_unversioned,
        "site_versioned": site_versioned,
        "site_unversioned": site_unversioned,
        "dist": dist,
        "config_etc": config_etc,
    }


def _esi_environment(
    tmp_path: Path, dirs: dict[str, Path], *,
    config_etc: bool = False, mode: str | None = None,
) -> dict[str, str]:
    """FOAM_API set and spelled differently from WM_PROJECT_VERSION -- the
    shape a real ESI (openfoam.com) v2412 install exports."""
    environment = {
        "HOME": str(tmp_path / "home"),
        "FOAM_API": "2412",
        "WM_PROJECT_VERSION": "v2412",
        "WM_PROJECT_SITE": str(tmp_path / "site"),
        "WM_PROJECT_DIR": str(tmp_path / "opt" / "openfoam2412"),
        "FOAM_ETC": str(dirs["dist"]),
    }
    if config_etc:
        environment["FOAM_CONFIG_ETC"] = str(dirs["config_etc"])
    if mode is not None:
        environment["FOAM_CONFIG_MODE"] = mode
    return environment


def _foundation_environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    """FOAM_API unset -- the shape a Foundation (openfoam.org) install such as
    ``~/.OpenFOAM/11`` exports; WM_PROJECT_VERSION alone names the directory.
    WM_PROJECT_SITE is pinned explicitly here, so this exercises the
    version-segment fallback only, not Foundation's site-root *default* --
    see ``test_foundation_style_site_root_defaults_from_wm_project_inst_dir``
    for that."""
    return {
        "HOME": str(tmp_path / "home"),
        "WM_PROJECT_VERSION": "2412",
        "WM_PROJECT_SITE": str(tmp_path / "site"),
        "WM_PROJECT_DIR": str(tmp_path / "opt" / "openfoam2412"),
        "FOAM_ETC": str(dirs["dist"]),
    }


def _expected_order(dirs: dict[str, Path], name: str) -> tuple[Path, ...]:
    return (
        dirs["user_versioned"] / name,
        dirs["user_unversioned"] / name,
        dirs["site_versioned"] / name,
        dirs["site_unversioned"] / name,
        dirs["dist"] / name,
    )


def test_the_full_five_location_order_for_an_esi_shaped_environment(tmp_path):
    """Matches a real `foamEtcFile -list controlDict` on ESI v2412, up to the
    fixture's own directory names."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    selected, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs),
    )
    assert candidates == _expected_order(dirs, "caseDicts/x")
    assert selected == dirs["dist"] / "caseDicts" / "x"


def test_the_full_five_location_order_for_a_foundation_shaped_environment(tmp_path):
    """Foundation builds do not export FOAM_API; the version segment falls
    back to WM_PROJECT_VERSION, which for that family IS the bare directory
    name (e.g. ``11``, not ``v11``)."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    env = _foundation_environment(tmp_path, dirs)
    assert "FOAM_API" not in env

    selected, candidates = find_etc_file("caseDicts/x", env)

    assert candidates == _expected_order(dirs, "caseDicts/x")
    assert selected == dirs["dist"] / "caseDicts" / "x"


def test_a_wm_project_version_qualified_user_file_is_ignored_when_foam_api_differs(tmp_path):
    """The regression a real installation exposed: a file at
    ``$HOME/.OpenFOAM/<WM_PROJECT_VERSION>`` must not be searched, let alone
    selected, when FOAM_API names a different directory. Native's own
    `userDir/$projectApi` is built from `$FOAM_API`; a `WM_PROJECT_VERSION`-
    qualified sibling has no native reader at all."""
    dirs = _layout(tmp_path)
    wrong_version_dir = dirs["user_unversioned"] / "v2412"
    (wrong_version_dir / "caseDicts").mkdir(parents=True)
    (wrong_version_dir / "caseDicts" / "x").write_text("wrong-version-shadow\n")
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")

    selected, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs),
    )

    assert wrong_version_dir / "caseDicts" / "x" not in candidates
    assert selected == dirs["dist"] / "caseDicts" / "x"


def test_a_site_file_shadows_the_distribution_file(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    (dirs["site_versioned"] / "caseDicts" / "x").write_text("site\n")
    selected, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs),
    )
    assert selected == dirs["site_versioned"] / "caseDicts" / "x"
    assert selected.read_text() == "site\n"


def test_an_unversioned_site_file_shadows_the_distribution_file(tmp_path):
    """The unversioned site fallback (`<site>/etc`, native's `groupDir/etc`)
    outranks the distribution even though it is lower priority than the
    versioned site directory."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    (dirs["site_unversioned"] / "caseDicts" / "x").write_text("site-unversioned\n")
    selected, _ = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs))
    assert selected == dirs["site_unversioned"] / "caseDicts" / "x"


def test_a_user_file_shadows_site_and_distribution(tmp_path):
    dirs = _layout(tmp_path)
    for key in ("dist", "site_versioned", "user_versioned"):
        (dirs[key] / "caseDicts" / "x").write_text(f"{key}\n")
    selected, _ = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs))
    assert selected == dirs["user_versioned"] / "caseDicts" / "x"


def test_every_candidate_is_reported_in_search_order(tmp_path):
    """A file appearing at a higher-priority location later changes which file
    the run reads. Phase 2 records the absent candidates as preconditions, so
    they must be reported even when nothing is there."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, candidates = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs))
    assert candidates == _expected_order(dirs, "caseDicts/x")


def test_a_missing_dependency_selects_nothing_but_still_reports_candidates(tmp_path):
    dirs = _layout(tmp_path)
    selected, candidates = find_etc_file(
        "caseDicts/absent", _esi_environment(tmp_path, dirs),
    )
    assert selected is None
    assert len(candidates) == 5


def test_the_closure_records_the_shadowing_file(tmp_path):
    """The public consequence: `inspected_files` must name the selected file."""
    from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry

    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("deltaT 1e-3;\n")
    (dirs["site_versioned"] / "caseDicts" / "x").write_text("deltaT 2e-3;\n")
    case = tmp_path / "case" / "system"
    case.mkdir(parents=True)
    dictionary = case / "controlDict"
    dictionary.write_text('#includeEtc "caseDicts/x"\n')

    result = resolve_effective_foam_entry(
        dictionary, "deltaT", bashrc=None, env=_esi_environment(tmp_path, dirs),
    )
    assert str(dirs["site_versioned"] / "caseDicts" / "x") in result.inspected_files
    assert str(dirs["dist"] / "caseDicts" / "x") not in result.inspected_files


# -- FOAM_CONFIG_ETC (mismatch 1) --------------------------------------------

def test_full_six_location_order_with_foam_config_etc_set(tmp_path):
    """FOAM_CONFIG_ETC inserts one more candidate, immediately before the
    distribution file -- not at the top of the chain."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    selected, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, config_etc=True),
    )
    assert candidates == (
        *_expected_order(dirs, "caseDicts/x")[:-1],
        dirs["config_etc"] / "caseDicts" / "x",
        dirs["dist"] / "caseDicts" / "x",
    )
    # Nothing shadows it above -- native still selects the distribution file.
    assert selected == dirs["dist"] / "caseDicts" / "x"


def test_foam_config_etc_is_selected_when_nothing_shadows_it(tmp_path):
    """Mismatch 1's regression: with FOAM_CONFIG_ETC set and no user/site
    shadow, native selects the override, not the distribution file."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    (dirs["config_etc"] / "caseDicts" / "x").write_text("config-etc-override\n")

    selected, _ = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, config_etc=True),
    )

    assert selected == dirs["config_etc"] / "caseDicts" / "x"


# -- FOAM_CONFIG_MODE (mismatch 2) -------------------------------------------

def test_foam_config_mode_o_excludes_user_and_group_entirely(tmp_path):
    """Mismatch 2's regression, the dangerous direction: under
    FOAM_CONFIG_MODE=o a user file must not be selected, and must not even
    appear in candidates -- native deliberately skips user/group, so
    recording that file as a dependency would take a precondition digest
    over a file with no bearing on the run."""
    dirs = _layout(tmp_path)
    (dirs["user_versioned"] / "caseDicts" / "x").write_text("user-shadow\n")
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")

    selected, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, mode="o"),
    )

    assert dirs["user_versioned"] / "caseDicts" / "x" not in candidates
    assert dirs["site_versioned"] / "caseDicts" / "x" not in candidates
    assert candidates == (dirs["dist"] / "caseDicts" / "x",)
    assert selected == dirs["dist"] / "caseDicts" / "x"


def test_foam_config_mode_u_searches_only_user_locations(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, mode="u"),
    )
    assert candidates == (
        dirs["user_versioned"] / "caseDicts" / "x",
        dirs["user_unversioned"] / "caseDicts" / "x",
    )


def test_foam_config_mode_go_searches_group_then_other_only(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, mode="go"),
    )
    assert candidates == (
        dirs["site_versioned"] / "caseDicts" / "x",
        dirs["site_unversioned"] / "caseDicts" / "x",
        dirs["dist"] / "caseDicts" / "x",
    )


def test_foam_config_mode_letter_order_does_not_change_search_order(tmp_path):
    """Native selects sections by checking `u`, then `g`, then `o`
    membership in a fixed sequence regardless of how the mode string spells
    them -- confirmed against the real binary with `-mode=ug` vs `-mode=gu`
    and `-mode=go` vs `-mode=og` (identical output both times)."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, ug = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs, mode="ug"))
    _, gu = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs, mode="gu"))
    _, go = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs, mode="go"))
    _, og = find_etc_file("caseDicts/x", _esi_environment(tmp_path, dirs, mode="og"))
    assert ug == gu
    assert go == og


def test_an_unrecognised_foam_config_mode_defaults_to_all_three(tmp_path):
    """A FOAM_CONFIG_MODE whose first character isn't u/g/o is not honoured at
    all -- ESI's own `case "$FOAM_CONFIG_MODE" in ([ugo]*) ...` -- so it must
    fall back to the full `ugo` search, exactly like an unset one."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    unset_selected, unset_candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs),
    )
    bogus_selected, bogus_candidates = find_etc_file(
        "caseDicts/x", _esi_environment(tmp_path, dirs, mode="z"),
    )
    assert bogus_candidates == unset_candidates == _expected_order(dirs, "caseDicts/x")
    assert bogus_selected == unset_selected == dirs["dist"] / "caseDicts" / "x"


# -- Foundation's site-root default -- source-verified only -----------------

def _foundation_inst_dir_layout(tmp_path: Path) -> dict[str, Path]:
    """A Foundation-shaped layout where the site root is derived from
    WM_PROJECT_INST_DIR (the parent of the versioned install) rather than
    from an explicit WM_PROJECT_SITE -- the branch `_foundation_environment`
    above never exercises."""
    inst_dir = tmp_path / "opt"
    user_versioned = tmp_path / "home" / ".OpenFOAM" / "11"
    user_unversioned = tmp_path / "home" / ".OpenFOAM"
    site_versioned = inst_dir / "site" / "11" / "etc"
    site_unversioned = inst_dir / "site" / "etc"
    dist = inst_dir / "OpenFOAM-11" / "etc"
    for directory in (
        user_versioned, user_unversioned, site_versioned, site_unversioned, dist,
    ):
        (directory / "caseDicts").mkdir(parents=True, exist_ok=True)
    return {
        "inst_dir": inst_dir,
        "user_versioned": user_versioned,
        "user_unversioned": user_unversioned,
        "site_versioned": site_versioned,
        "site_unversioned": site_unversioned,
        "dist": dist,
    }


def _foundation_inst_dir_environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    """No FOAM_API, no WM_PROJECT_SITE: WM_PROJECT_INST_DIR is the only site
    hint, exactly as Foundation's own etc/bashrc exports it. Source-verified
    against ``raw.githubusercontent.com/OpenFOAM/OpenFOAM-dev/master/{
    bin/foamEtcFile,etc/bashrc}`` (fetched 2026-09-22): bashrc's own comment
    reads "unset is equivalent to $WM_PROJECT_INST_DIR/site", and
    bin/foamEtcFile's own ``siteDir="${WM_PROJECT_SITE:-$prefixDir/site}"``
    where ``prefixDir`` is the parent of the versioned project directory.
    **Not** verified against a running Foundation installation -- none exists
    on this machine."""
    return {
        "HOME": str(tmp_path / "home"),
        "WM_PROJECT_VERSION": "11",
        "WM_PROJECT_INST_DIR": str(dirs["inst_dir"]),
        "WM_PROJECT_DIR": str(dirs["inst_dir"] / "OpenFOAM-11"),
    }


def test_foundation_style_site_root_defaults_from_wm_project_inst_dir(tmp_path):
    """Source-verified only (see `_foundation_inst_dir_environment`): the
    previous version of this function applied ESI's site-root rule
    (`$WM_PROJECT_DIR/site`) unconditionally, which is wrong for Foundation's
    documented `$WM_PROJECT_INST_DIR/site` default -- a sibling of the
    versioned install, not a child of it."""
    dirs = _foundation_inst_dir_layout(tmp_path)
    (dirs["site_versioned"] / "caseDicts" / "x").write_text("site\n")
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")

    selected, candidates = find_etc_file(
        "caseDicts/x", _foundation_inst_dir_environment(tmp_path, dirs),
    )

    assert selected == dirs["site_versioned"] / "caseDicts" / "x"
    assert dirs["dist"] / "caseDicts" / "x" in candidates
    # The wrong (ESI-shaped) location -- $WM_PROJECT_DIR/site -- must not be
    # searched under this family's rule.
    wrong_root = dirs["inst_dir"] / "OpenFOAM-11" / "site"
    assert not any(str(wrong_root) in str(candidate) for candidate in candidates)


def test_foundation_style_environment_with_neither_site_hint_adds_no_site_candidate(tmp_path):
    """Neither WM_PROJECT_SITE nor WM_PROJECT_INST_DIR present, and FOAM_API
    absent (so the ESI default does not apply either): no site candidate is
    added at all, rather than guessing which family's rule to fall back to.
    An honest gap, per this function's own documented rule against
    unverified defaults."""
    dirs = _foundation_inst_dir_layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    environment = _foundation_inst_dir_environment(tmp_path, dirs)
    del environment["WM_PROJECT_INST_DIR"]

    _, candidates = find_etc_file("caseDicts/x", environment)

    assert not any("site" in str(candidate) for candidate in candidates)
