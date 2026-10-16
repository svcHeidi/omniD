"""The sealed-wall key: each of the three PDE myocardium solvers requires it, a solver that does not read it is not
asked for it, and the bath's heart phiE trace is one of the two words the C++ accepts."""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
from omnidriver.openfoam.case_rules import rule_diagnostics

SEALED = "sealedHeartBoundary"
TRACE = "bathHeartPhiETrace"


def _errors(context):
    found = rule_diagnostics(_ELECTRO_ENTRIES_BY_PATH.values(), context, document="constant/electroProperties")
    return {item.field: item.message for item in found}


@pytest.mark.parametrize("solver", ["monodomainSolver", "bidomainSolver", "eikonalSolver"])
def test_a_pde_or_eikonal_solver_requires_the_sealed_wall_key(solver):
    assert SEALED in _errors({"myocardiumSolver": solver})


def test_a_single_cell_run_is_not_asked_for_it():
    assert SEALED not in _errors({"myocardiumSolver": "singleCellSolver"})


def test_the_bath_heart_phie_trace_is_one_of_the_two_words_the_cxx_accepts():
    errors = _errors({"myocardiumSolver": "bidomainSolver", SEALED: "true", TRACE: "conormal"})
    assert "conormal" in errors[TRACE]
    assert TRACE not in _errors({"myocardiumSolver": "bidomainSolver", SEALED: "true", TRACE: "global"})
