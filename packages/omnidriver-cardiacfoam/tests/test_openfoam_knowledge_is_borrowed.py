"""What OpenFOAM knows (its ODE solvers, the stability of its ddt schemes) is held by the OpenFOAM layer, and cardiacFOAM uses it from there."""
from __future__ import annotations

from omnidriver.cardiacfoam import validation
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.openfoam.scheme_tables import ODE_SOLVER_MENU


def test_every_ode_solver_key_offers_the_names_openfoams_ode_solver_table_registers():
    solvers = [entry for entry in CardiacFoamPlugin().get_dict_entries() if entry.driver_path.endswith(".solver") and "RKF45" in entry.enum_values]
    assert len(solvers) == 2
    assert all(entry.enum_values == ODE_SOLVER_MENU for entry in solvers)
    assert len(ODE_SOLVER_MENU) == 13


def test_the_ddt_stability_limits_are_not_restated_here():
    assert not hasattr(validation, "_DDT_STABILITY_LIMIT")
