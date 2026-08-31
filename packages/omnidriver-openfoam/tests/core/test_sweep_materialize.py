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
#     Moved from omnidriver/tests/core/test_sweep_materialize.py (Phase 2
#     Task 4): this is the one test in that module that asserts on OpenFOAM
#     output directly (omnidriver.openfoam.mesh_provisioning's
#     default_block_mesh_dict_text), rather than on materialize_case's own
#     core-owned routing/dispatch. The rest of that module stays in
#     omnidriver/tests/core/ -- it fails core-only for an unrelated reason
#     (the default cardiacFoam plugin selection), not because it needs
#     OpenFOAM.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text
from omnidriver.sweep_materialize import materialize_case


def test_materialize_case_honours_dx_for_spatial_solver(tmp_path):
    case_dir = tmp_path / "TNNP_monodomain_fine"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "monodomainSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None, "dx": 0.0004,
        },
    )
    written = (case_dir / "system" / "blockMeshDict").read_text()
    assert written == default_block_mesh_dict_text(dx_m=0.0004)
