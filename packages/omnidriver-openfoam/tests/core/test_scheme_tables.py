"""OpenFOAM's scheme and ODE-solver tables: read from ``$FOAM_SRC`` (never searched for), cached under the scratch root by a digest."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from omnidriver.openfoam import scheme_tables
from omnidriver.openfoam.case_rules import rule_diagnostics
from omnidriver.openfoam.record_key_validation import listed_entry
from omnidriver.openfoam.scheme_tables import (
    cached_selection_tables, foam_source_root, openfoam_table_entry, scan_selection_tables, snapshot, snapshot_diagnostics,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "openfoam_v2412_src"


@pytest.fixture
def source(tmp_path) -> Path:
    shutil.copytree(_FIXTURES, tmp_path / "src")
    return tmp_path / "src"


def test_the_source_root_is_foam_src_from_the_supplied_environment_and_nothing_else(tmp_path):
    assert foam_source_root({}) is None
    assert foam_source_root({"WM_PROJECT_DIR": str(tmp_path)}) is None
    assert foam_source_root({"FOAM_SRC": str(tmp_path)}) == tmp_path.resolve()


def test_the_scan_reads_the_scheme_tables_and_the_ode_solvers_of_the_libraries_it_names(source):
    tables = scan_selection_tables(source)
    assert tables.schemes["ddtSchemes"]["backward"] == "backwardDdtScheme"
    assert tables.ode_solvers == {"Euler": "Euler"}
    assert tables.menus()["ODESolver"] == ["Euler"]


def test_a_library_outside_the_named_ones_is_not_read(source):
    (source / "other").mkdir()
    (source / "other" / "oddScheme.C").write_text("makeFvDdtScheme(oddDdtScheme)\n")
    assert "oddDdtScheme" not in {cls for names in scan_selection_tables(source).schemes.values() for cls in names.values()}


def test_a_scan_is_cached_under_the_supplied_scratch_root_by_digest_and_follows_the_source(source, tmp_path):
    scratch = tmp_path / "scratch"
    first = cached_selection_tables(source, cache_root=scratch)
    (cached,) = (scratch / "openfoam-selection-scan").glob("*.json")
    assert json.loads(cached.read_text())["digest"] == first.digest
    scheme_tables._MEMO.clear()
    assert cached_selection_tables(source, cache_root=scratch) == first

    changed = source / "finiteVolume/finiteVolume/ddtSchemes/EulerDdtScheme/EulerDdtSchemes.C"
    changed.write_text(changed.read_text() + "\nmakeFvDdtScheme(backwardDdtScheme)\n")
    assert cached_selection_tables(source, cache_root=scratch).digest != first.digest
    assert len(list((scratch / "openfoam-selection-scan").glob("*.json"))) == 2


def test_an_unreadable_cache_file_is_rescanned_and_rewritten(source, tmp_path):
    scratch = tmp_path / "scratch"
    expected = cached_selection_tables(source, cache_root=scratch)
    (cached,) = (scratch / "openfoam-selection-scan").glob("*.json")
    cached.write_text("{not json")
    scheme_tables._MEMO.clear()
    assert cached_selection_tables(source, cache_root=scratch) == expected
    assert json.loads(cached.read_text())["digest"] == expected.digest


def test_no_cache_is_written_when_no_scratch_root_is_supplied(source, tmp_path):
    assert cached_selection_tables(source, cache_root=None).schemes
    assert not list(tmp_path.rglob("openfoam-selection-scan"))


def test_the_snapshot_records_the_version_and_the_digest_of_the_source_it_scanned():
    menus = snapshot()
    assert menus["openfoam_version"] and len(menus["source_digest"]) == 64
    assert {"ddtSchemes", "gradSchemes", "divSchemes", "laplacianSchemes", "snGradSchemes", "interpolationSchemes", "ODESolver"} <= set(menus["tables"])
    assert all(names == sorted(names) and names for names in menus["tables"].values())


_ODE = "$C.solver"


def _ode_entry():
    return openfoam_table_entry("ODESolver", driver_path=_ODE, description="an ODE solver")


def _with_extra_ode_solver(source: Path) -> Path:
    extra = source / "ODE/ODESolvers/extraSolver"
    extra.mkdir(parents=True)
    (extra / "extraSolver.H").write_text('class extraSolver : public ODESolver\n{\npublic:\n    TypeName("extraSolver");\n};\n')
    (extra / "extraSolver.C").write_text("addToRunTimeSelectionTable(ODESolver, extraSolver, dictionary);\n")
    return source


@pytest.fixture
def no_source(monkeypatch):
    for variable in ("FOAM_SRC", "WM_PROJECT_VERSION", "OMNIDRIVER_SCRATCH_DIR"):
        monkeypatch.delenv(variable, raising=False)


def test_a_name_the_supplied_source_registers_is_accepted_though_the_snapshot_lacks_it(source, monkeypatch, no_source):
    monkeypatch.setenv("FOAM_SRC", str(_with_extra_ode_solver(source)))
    assert "extraSolver" not in snapshot()["tables"]["ODESolver"]
    assert rule_diagnostics([_ode_entry()], {"solver": "extraSolver"}, document="constant/x") == []
    (refused,) = rule_diagnostics([_ode_entry()], {"solver": "Rosenbrock34"}, document="constant/x")
    assert refused.level == "error" and "extraSolver" in refused.detail["rule"]["menu"]
    listed = listed_entry("constant/x", "solver", _ode_entry())
    assert "extraSolver" in listed["menu"] and "scanned from FOAM_SRC" in listed["menu_source"]


def test_without_a_source_nothing_is_refused_on_the_snapshot_and_the_listing_says_so(no_source):
    assert rule_diagnostics([_ode_entry()], {"solver": "extraSolver"}, document="constant/x") == []
    listed = listed_entry("constant/x", "solver", _ode_entry())
    assert listed["value_kind"] == "word" and listed["menu"] == snapshot()["tables"]["ODESolver"]
    assert snapshot()["openfoam_version"] in listed["menu_source"] and "not judged" in listed["menu_source"]


def test_a_running_version_other_than_the_snapshots_is_a_note(source, monkeypatch, no_source):
    assert snapshot_diagnostics({"WM_PROJECT_VERSION": snapshot()["openfoam_version"]}) == ()
    (note,) = snapshot_diagnostics({"WM_PROJECT_VERSION": "v9999"})
    assert (note.level, note.code) == ("info", "openfoam_snapshot_version_mismatch") and "v9999" in note.message
    assert snapshot_diagnostics({"WM_PROJECT_VERSION": "v9999", "FOAM_SRC": str(source)}) == ()
