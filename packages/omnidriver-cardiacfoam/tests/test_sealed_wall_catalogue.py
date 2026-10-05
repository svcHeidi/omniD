"""The insulated-wall keys: each of the three PDE myocardium solvers requires them, a menu bounds the wall
trace, and a solver that reads neither is not asked for them."""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.record_key_validation import _ELECTRO_ENTRIES_BY_PATH
from omnidriver.openfoam.case_rules import rule_diagnostics

SEALED = "sealedHeartBoundary"
TRACE = "sealedWallTrace"


def _errors(context):
    found = rule_diagnostics(_ELECTRO_ENTRIES_BY_PATH.values(), context, document="constant/electroProperties")
    return {item.field: item.message for item in found}


@pytest.mark.parametrize("solver", ["monodomainSolver", "bidomainSolver", "eikonalSolver"])
def test_a_pde_or_eikonal_solver_requires_both_keys(solver):
    errors = _errors({"myocardiumSolver": solver})
    assert SEALED in errors and TRACE in errors


def test_a_single_cell_run_is_not_asked_for_them():
    errors = _errors({"myocardiumSolver": "singleCellSolver"})
    assert SEALED not in errors and TRACE not in errors


def test_the_wall_trace_is_one_of_the_two_words_the_cxx_accepts():
    errors = _errors({"myocardiumSolver": "monodomainSolver", SEALED: "false", TRACE: "neumann"})
    assert "neumann" in errors[TRACE]
    ok = _errors({"myocardiumSolver": "monodomainSolver", SEALED: "true", TRACE: "conormal"})
    assert SEALED not in ok and TRACE not in ok
