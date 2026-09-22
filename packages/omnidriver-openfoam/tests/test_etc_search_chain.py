"""An etc dependency must be the file the native runtime would select.

`#includeEtc "caseDicts/x"` was resolved as `$FOAM_ETC/caseDicts/x` and nothing
else. Native `findEtcFile` searches five locations -- user, then site, then
distribution, each with a versioned and (for user/site) an unversioned form --
so a site or user override is read by the solver while the inspector recorded
the vendor file. Dependency closure then names a file the run did not use --
and a precondition digest over that file proves nothing about the run.

These fixtures are directory layouts, not an OpenFOAM installation. They assert
which candidate is selected and which candidates were searched, not what
foamDictionary would print. The native comparison lives in
``tests/core/test_effective_dictionary.py``, guarded by the same ``@native``
marker as the rest of that file's runtime-backed tests, so it runs only when
an OpenFOAM installation is actually discoverable.

Corrected 2026-09-22, second pass: the first version of this file modelled
only three locations (versioned user, versioned site, distribution) and built
the user/site directories from ``WM_PROJECT_VERSION``. Measured against a real
ESI v2412 install, native's own `foamEtcFile -list` names five locations, the
user/site ones qualified by ``FOAM_API`` (not ``WM_PROJECT_VERSION`` -- they
differ on ESI builds, e.g. ``2412`` vs ``v2412``), plus unversioned user and
site fallbacks. `test_a_wm_project_version_qualified_user_file_is_ignored...`
below is the fixture form of the regression that measurement caught: the first
draft's own `$HOME/.OpenFOAM/v2412` candidate is a location native never
reads, so a file placed there was selected by the driver while the real run
kept reading straight through to the distribution file underneath it.
"""

from pathlib import Path

from omnidriver.openfoam.effective_dictionary import find_etc_file


def _layout(tmp_path: Path) -> dict[str, Path]:
    """The five candidate directories, named after `foamEtcFile`'s own
    `dirList` construction (`userDir`, `groupDir`, `projectDir`)."""
    user_versioned = tmp_path / "home" / ".OpenFOAM" / "2412"
    user_unversioned = tmp_path / "home" / ".OpenFOAM"
    site_versioned = tmp_path / "site" / "2412" / "etc"
    site_unversioned = tmp_path / "site" / "etc"
    dist = tmp_path / "opt" / "openfoam2412" / "etc"
    for directory in (
        user_versioned, user_unversioned, site_versioned, site_unversioned, dist,
    ):
        (directory / "caseDicts").mkdir(parents=True, exist_ok=True)
    return {
        "user_versioned": user_versioned,
        "user_unversioned": user_unversioned,
        "site_versioned": site_versioned,
        "site_unversioned": site_unversioned,
        "dist": dist,
    }


def _esi_environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    """FOAM_API set and spelled differently from WM_PROJECT_VERSION -- the
    shape a real ESI (openfoam.com) v2412 install exports."""
    return {
        "HOME": str(tmp_path / "home"),
        "FOAM_API": "2412",
        "WM_PROJECT_VERSION": "v2412",
        "WM_PROJECT_SITE": str(tmp_path / "site"),
        "WM_PROJECT_DIR": str(tmp_path / "opt" / "openfoam2412"),
        "FOAM_ETC": str(dirs["dist"]),
    }


def _foundation_environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    """FOAM_API unset -- the shape a Foundation (openfoam.org) install such as
    ``~/.OpenFOAM/11`` exports; WM_PROJECT_VERSION alone names the directory."""
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
