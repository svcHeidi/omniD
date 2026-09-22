"""An etc dependency must be the file the native runtime would select.

`#includeEtc "caseDicts/x"` was resolved as `$FOAM_ETC/caseDicts/x` and nothing
else. Native `findEtcFile` searches user, then site, then distribution
locations, so a site override is read by the solver while the inspector records
the vendor file. Dependency closure then names a file the run did not use --
and a precondition digest over that file proves nothing about the run.

These fixtures are directory layouts, not an OpenFOAM installation. They assert
which candidate is selected and which candidates were searched, not what
foamDictionary would print.
"""

from pathlib import Path

from omnidriver.openfoam.effective_dictionary import find_etc_file


def _layout(tmp_path: Path) -> dict[str, Path]:
    user = tmp_path / "home" / ".OpenFOAM" / "2412"
    site = tmp_path / "site" / "2412" / "etc"
    dist = tmp_path / "opt" / "openfoam2412" / "etc"
    for directory in (user, site, dist):
        (directory / "caseDicts").mkdir(parents=True)
    return {"user": user, "site": site, "dist": dist}


def _environment(tmp_path: Path, dirs: dict[str, Path]) -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "home"),
        "WM_PROJECT_VERSION": "2412",
        "WM_PROJECT_SITE": str(tmp_path / "site"),
        "WM_PROJECT_DIR": str(tmp_path / "opt" / "openfoam2412"),
        "FOAM_ETC": str(dirs["dist"]),
    }


def test_the_distribution_file_is_selected_when_it_is_the_only_one(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    selected, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["dist"] / "caseDicts" / "x"
    assert selected in candidates


def test_a_site_file_shadows_the_distribution_file(tmp_path):
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    (dirs["site"] / "caseDicts" / "x").write_text("site\n")
    selected, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["site"] / "caseDicts" / "x"
    assert selected.read_text() == "site\n"


def test_a_user_file_shadows_both(tmp_path):
    dirs = _layout(tmp_path)
    for key in ("dist", "site", "user"):
        (dirs[key] / "caseDicts" / "x").write_text(f"{key}\n")
    selected, _ = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert selected == dirs["user"] / "caseDicts" / "x"


def test_every_candidate_is_reported_in_search_order(tmp_path):
    """A file appearing at a higher-priority location later changes which file
    the run reads. Phase 2 records the absent candidates as preconditions, so
    they must be reported even when nothing is there."""
    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("vendor\n")
    _, candidates = find_etc_file("caseDicts/x", _environment(tmp_path, dirs))
    assert candidates == (
        dirs["user"] / "caseDicts" / "x",
        dirs["site"] / "caseDicts" / "x",
        dirs["dist"] / "caseDicts" / "x",
    )


def test_a_missing_dependency_selects_nothing_but_still_reports_candidates(tmp_path):
    dirs = _layout(tmp_path)
    selected, candidates = find_etc_file("caseDicts/absent", _environment(tmp_path, dirs))
    assert selected is None
    assert len(candidates) == 3


def test_the_closure_records_the_shadowing_file(tmp_path):
    """The public consequence: `inspected_files` must name the selected file."""
    from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry

    dirs = _layout(tmp_path)
    (dirs["dist"] / "caseDicts" / "x").write_text("deltaT 1e-3;\n")
    (dirs["site"] / "caseDicts" / "x").write_text("deltaT 2e-3;\n")
    case = tmp_path / "case" / "system"
    case.mkdir(parents=True)
    dictionary = case / "controlDict"
    dictionary.write_text('#includeEtc "caseDicts/x"\n')

    result = resolve_effective_foam_entry(
        dictionary, "deltaT", bashrc=None, env=_environment(tmp_path, dirs),
    )
    assert str(dirs["site"] / "caseDicts" / "x") in result.inspected_files
    assert str(dirs["dist"] / "caseDicts" / "x") not in result.inspected_files
