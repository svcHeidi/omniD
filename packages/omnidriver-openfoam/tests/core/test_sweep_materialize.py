"""Sweep-materialize test that asserts on OpenFOAM output directly, unlike
its sibling tests in omnidriver's own core test tree, which assert only on
materialize_case's core-owned routing/dispatch."""

import pytest

from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text
from omnidriver.sweep_materialize import materialize_case


def test_materialize_case_honours_dx_for_spatial_solver(tmp_path):
    pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason=(
            "materialize_case()'s only real (non-refusing) implementation is "
            "gated to org.cardiacfoam (compatibility.absent_materialize_sweep_case); "
            "omnidriver-cardiacfoam is not installed"
        ),
    )
    # Pins the adapter explicitly: the registry has no unique answer once
    # cardiacfoam and openfoam-environment are both installed.
    from omnidriver.core.plugin_interface import driver_context as _driver_context
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    context = _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:sweep_materialize",
    )

    case_dir = tmp_path / "TNNP_monodomain_fine"
    materialize_case(
        case_dir=case_dir,
        routed={
            "electro_selectors": {"myocardiumSolver": "monodomainSolver", "tissue": "epicardialCells", "ionicModel": "TNNP"},
            "physics_selectors": {"type": "electroModel"},
            "electro_overrides": {}, "physics_overrides": {},
            "delta_t": None, "end_time": None, "dx": 0.0004,
        },
        driver_context=context,
    )
    written = (case_dir / "system" / "blockMeshDict").read_text()
    assert written == default_block_mesh_dict_text(dx_m=0.0004)
