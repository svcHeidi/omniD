"""OpenFOAM's scheme and ODE-solver tables: read from ``$FOAM_SRC`` (never searched for), cached under the scratch root by a digest."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from omnidriver.openfoam import scheme_tables
from omnidriver.openfoam.scheme_tables import (
    cached_selection_tables, committed_menus, foam_source_root, scan_selection_tables,
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
    assert tables.ode_solvers == {"Euler": "Euler", "RKF45": "RKF45"}
    assert tables.menus()["ODESolver"] == ["Euler", "RKF45"]


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


def test_the_committed_menus_are_a_scan_of_one_named_version():
    menus = committed_menus()
    assert menus["openfoam_version"]
    assert {"ddtSchemes", "gradSchemes", "divSchemes", "laplacianSchemes", "snGradSchemes", "interpolationSchemes", "ODESolver"} <= set(menus["tables"])
    assert all(names == sorted(names) and names for names in menus["tables"].values())
