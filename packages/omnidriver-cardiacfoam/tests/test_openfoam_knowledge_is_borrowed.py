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


def test_the_ddt_stability_bounds_are_not_restated_in_notes_or_docstrings():
    import re

    from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS

    texts = [entry.notes for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values() for entry in group]
    texts.append(validation._evaluate_pvj_stability.__doc__)
    restated = re.compile(r"\b[24]\b[^.]{0,40}\b(Euler|backward)\b|\b(Euler|backward)\b[^.]{0,20}\b[24]\b")
    assert not [text for text in texts if restated.search(text)]
