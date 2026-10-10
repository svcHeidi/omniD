"""What OpenFOAM knows (its ODE solvers, the stability of its ddt schemes) is held by the OpenFOAM layer, and cardiacFOAM uses it from there."""
from __future__ import annotations

from omnidriver.cardiacfoam import validation
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.openfoam.scheme_tables import OpenFoamTableEntry


def test_every_ode_solver_key_takes_its_menu_from_openfoams_ode_solver_table():
    solvers = [entry for entry in CardiacFoamPlugin().get_dict_entries() if entry.driver_path.endswith(".solver")]
    assert len(solvers) == 3
    assert all(isinstance(entry, OpenFoamTableEntry) and entry.table == "ODESolver" for entry in solvers)
    assert {entry.value_kind for entry in solvers} == {"word"}


def test_the_ddt_stability_limits_are_not_restated_here():
    assert not hasattr(validation, "_DDT_STABILITY_LIMIT")
