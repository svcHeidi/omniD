#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_sweep_materialize
#
# Description
#     Tests sweep case materialization via build_and_launch.
#
#     Moved from omnidriver/tests/core/test_sweep_materialize.py (Phase 2
#     Task M2): every test in that module asserted
#     constant/electroProperties contents and that the generated Allrun
#     invokes cardiacFoam -- cardiacFoam vocabulary, not core's own
#     routing/dispatch. A sibling test in this same module,
#     test_materialize_case_honours_dx_for_spatial_solver, had already moved
#     to omnidriver-openfoam/tests/core/test_sweep_materialize.py for
#     asserting OpenFOAM blockMeshDict output specifically; this is the rest
#     of that module, one step further down the same seam.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.sweep_materialize import materialize_case

# Every case below is a cardiacFoam case, so it says so. materialize_case only
# falls back to the ambient default when no context is supplied, and that
# default has no single answer once a second adapter is installed alongside
# this one (future/ENVIRONMENT_CONTRACT.md §12).
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:sweep_materialize")


def test_materialize_case_writes_dict_files_and_allrun_only(tmp_path):
    case_dir = tmp_path / "TNNP_1e-06"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {},
            "physics_overrides": {},
            "delta_t": 1e-6,
            "end_time": None,
        },
        driver_context=_CTX,
    )
    assert (case_dir / "constant" / "electroProperties").exists()
    assert (case_dir / "constant" / "physicsProperties").exists()
    assert (case_dir / "system" / "controlDict").exists()
    assert "1e-06" in (case_dir / "system" / "controlDict").read_text()

    allrun = case_dir / "Allrun"
    assert allrun.exists()
    assert allrun.stat().st_mode & 0o111  # executable
    assert not (case_dir / "workflow_contract.json").exists()


def test_materialize_case_allrun_mode_on_a_fresh_case_is_0o755(tmp_path):
    """Characterization, ahead of Phase 3 Task 10 folding this write into
    the channel: pin the exact mode (not just "has some execute bit") and
    the exact content, on a case_dir that does not exist yet. Captured
    against the pre-Task-10 sweep.py::materialize_case, which write_text's
    Allrun then ORs S_IEXEC|S_IXGRP|S_IXOTH onto whatever mode resulted
    from that write -- under this environment's umask (022), a fresh file
    is created 0o644, so 0o644 | 0o111 == 0o755. A mode-only or digest-only
    check would miss either half of the trap Task 10 names."""
    case_dir = tmp_path / "fresh_case"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None,
        },
        driver_context=_CTX,
    )
    allrun = case_dir / "Allrun"
    assert allrun.stat().st_mode & 0o777 == 0o755
    assert allrun.read_text() == "#!/bin/sh\ncardiacFoam\n"


def test_materialize_case_allrun_mode_when_allrun_already_existed(tmp_path):
    """Same trap, the other half: a case_dir reused for a second
    materialize_case call (sweep.py always passes overwrite=True to
    build_and_launch) must preserve whatever read/write bits the existing
    Allrun already carried, only adding the execute bits -- not silently
    reset to a fixed mode regardless of what was there."""
    case_dir = tmp_path / "reused_case"
    case_dir.mkdir()
    allrun = case_dir / "Allrun"
    allrun.write_text("#!/bin/sh\nold\n")
    allrun.chmod(0o700)
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None,
        },
        driver_context=_CTX,
    )
    assert allrun.stat().st_mode & 0o777 == 0o711  # 0o700 | 0o111
    assert allrun.read_text() == "#!/bin/sh\ncardiacFoam\n"


def test_materialize_case_two_cases_do_not_collide(tmp_path):
    materialize_case(
        case_dir=tmp_path / "caseA",
        routed={"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
                "physics_selectors": {"type": "electroModel"}, "electro_overrides": {}, "physics_overrides": {},
                "delta_t": None, "end_time": None},
        driver_context=_CTX,
    )
    materialize_case(
        case_dir=tmp_path / "caseB",
        routed={"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "BuenoOrovio"},
                "physics_selectors": {"type": "electroModel"}, "electro_overrides": {}, "physics_overrides": {},
                "delta_t": None, "end_time": None},
        driver_context=_CTX,
    )
    a = (tmp_path / "caseA" / "constant" / "electroProperties").read_text()
    b = (tmp_path / "caseB" / "constant" / "electroProperties").read_text()
    assert "TNNP" in a and "BuenoOrovio" not in a
    assert "BuenoOrovio" in b and "TNNP" not in b


def test_materialize_case_runs_block_mesh_first_for_spatial_solver(tmp_path):
    # monodomainSolver needs a real fvMesh; provision_mesh writes a default
    # blockMeshDict for it (see mesh_provisioning.py), so the generated
    # Allrun must run blockMesh before cardiacFoam -- otherwise cardiacFoam
    # crashes with "Cannot find file points in polyMesh" (the exact failure
    # this fix addresses, see project_driverfoam_sweep_bugs_found memory).
    case_dir = tmp_path / "TNNP_monodomain"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "monodomainSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None,
        },
        driver_context=_CTX,
    )
    assert (case_dir / "system" / "blockMeshDict").exists()
    allrun_text = (case_dir / "Allrun").read_text()
    assert allrun_text.index("blockMesh") < allrun_text.index("cardiacFoam")


def test_materialize_case_raises_on_invalid_combination(tmp_path):
    with pytest.raises(ValueError, match="tissue"):
        materialize_case(
            case_dir=tmp_path / "bad_case",
            routed={"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "myocyte", "ionicModel": "TNNP"},
                    "physics_selectors": {"type": "electroModel"}, "electro_overrides": {}, "physics_overrides": {},
                    "delta_t": None, "end_time": None},
            driver_context=_CTX,
        )
