"""OpenFOAM output produced by generic sweep materialization."""

import pytest

from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text
from omnidriver.sweep_materialize import materialize_case


def test_materialize_case_honours_dx_for_spatial_solver(tmp_path):
    pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason=(
            "materialize_case()'s only real (non-refusing) implementation is "
            "gated to org.cardiacfoam (compatibility.legacy_materialize_sweep_case); "
            "omnidriver-cardiacfoam is not installed"
        ),
    )
    from omnidriver.core.plugin_interface import default_driver_context

    case_dir = tmp_path / "TNNP_monodomain_fine"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "monodomainSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None, "dx": 0.0004,
        },
        driver_context=default_driver_context(),
    )
    written = (case_dir / "system" / "blockMeshDict").read_text()
    assert written == default_block_mesh_dict_text(dx_m=0.0004)
