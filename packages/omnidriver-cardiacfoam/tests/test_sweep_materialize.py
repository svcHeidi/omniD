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
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.sweep_materialize import materialize_case

# Two adapters are installed side by side, so there is no ambient default.
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
    """Under umask 022 a fresh Allrun is 0o644, and the execute bits OR onto it."""
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
    assert allrun.read_text() == "#!/bin/sh\nblockMesh\ncardiacFoam\n"


def test_materialize_case_allrun_mode_when_allrun_already_existed(tmp_path):
    """An existing Allrun keeps its read/write bits; only execute bits are added."""
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
    assert allrun.read_text() == "#!/bin/sh\nblockMesh\ncardiacFoam\n"


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
    # Without blockMesh first, cardiacFoam fails with "Cannot find file points in polyMesh".
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


def test_materialize_case_runs_block_mesh_first_for_single_cell_solver(tmp_path):
    case_dir = tmp_path / "TNNP_singleCell"
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
    block_mesh_dict = case_dir / "system" / "blockMeshDict"
    assert block_mesh_dict.exists()
    assert "hex (0 1 2 3 4 5 6 7) (1 1 1)" in block_mesh_dict.read_text()
    assert not (case_dir / "constant" / "polyMesh").exists()
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
