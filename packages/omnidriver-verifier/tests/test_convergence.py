"""The shared norm, the order fit and the comparison table, on synthetic grids whose answers are known by hand."""
from __future__ import annotations

import math

import pytest

from omnidriver.verifier.convergence import comparison_table, error_norms, exact_values, observed_orders
from omnidriver.verifier.problem import ProblemError, load_problem


def test_the_exact_field_is_the_problems_own_expression():
    problem = load_problem("fda_monodomain")
    assert exact_values(problem, 1, "V", 0.0, [(0.0,), (0.5,), (1.0,)]) == pytest.approx([1.0, 0.0, -1.0], abs=1e-15)
    [u2] = exact_values(problem, 3, "u2", 0.2, [(0.5, 0.5, 0.5)])
    assert u2 == pytest.approx(1 / (1.2 * math.sqrt(1 + 0.5 * 0.25 * 0.125)))


def test_the_norm_weights_by_volume_and_normalises_by_the_total():
    problem = load_problem("fda_monodomain")
    exact = [1.0, 2.0, 3.0]
    values = [1.1, 1.8, 3.0]
    weights = [1.0, 3.0, 4.0]
    norms = error_norms(problem, values, exact, weights)
    assert norms["L1"] == pytest.approx((0.1 + 3 * 0.2) / 8)
    assert norms["L2"] == pytest.approx(math.sqrt((0.01 + 3 * 0.04) / 8))
    assert norms["Linf"] == pytest.approx(0.2)


def test_equal_weights_give_the_rms():
    problem = load_problem("fda_monodomain")
    errors = [0.3, -0.4]
    norms = error_norms(problem, errors, [0.0, 0.0], [0.5, 0.5])
    assert norms["L2"] == pytest.approx(math.sqrt((0.09 + 0.16) / 2))


def test_mismatched_lengths_are_refused():
    with pytest.raises(ProblemError):
        error_norms(load_problem("fda_monodomain"), [1.0], [1.0, 2.0], [1.0])


def test_a_second_order_error_has_order_two():
    spacings = [0.1, 0.05, 0.025, 0.0125]
    orders = observed_orders(spacings, [3 * h**2 for h in spacings])
    assert orders["successive"] == pytest.approx([2, 2, 2])
    assert orders["least_squares"] == pytest.approx(2)


def _result(problem: dict, solver: str, scale: float, power: float) -> dict:
    ladder = problem["refinement"]["hex"]
    return {
        "solver": solver, "problem": problem["id"], "mesh": "hex", "stated": {"space": 2},
        "levels": [
            {"dimension": 1, "cells_per_axis": n, "dt": dt, "steps": steps,
             "errors": {"V": {kind: scale * (1 / n) ** power for kind in ("L1", "L2", "Linf")}}}
            for n, dt, steps in zip(ladder["cells_per_axis"], ladder["dt"], ladder["steps"])
        ],
    }


def test_the_table_carries_each_solvers_levels_orders_and_statement():
    problem = load_problem("fda_monodomain")
    table = comparison_table(problem, [_result(problem, "a", 1.0, 2), _result(problem, "b", 2.0, 1)])
    by_solver = {row["solver"]: row for row in table["rows"]}
    assert by_solver["a"]["least_squares_order"]["V"]["L2"] == pytest.approx(2)
    assert by_solver["b"]["least_squares_order"]["V"]["Linf"] == pytest.approx(1)
    first, second = by_solver["a"]["levels"][:2]
    assert first["observed_order"]["V"]["L2"] is None
    assert second["observed_order"]["V"]["L2"] == pytest.approx(2)
    assert first["time"] == pytest.approx(22 * 0.00892857)
    assert by_solver["a"]["stated"] == {"space": 2}


def test_a_level_off_the_ladder_is_refused():
    problem = load_problem("fda_monodomain")
    result = _result(problem, "a", 1.0, 2)
    result["levels"][0]["dt"] = 0.01
    with pytest.raises(ProblemError) as caught:
        comparison_table(problem, [result])
    assert "off the problem's hex ladder" in str(caught.value)


def test_a_norm_the_problem_does_not_name_is_refused():
    problem = load_problem("fda_monodomain")
    result = _result(problem, "a", 1.0, 2)
    result["levels"][0]["errors"]["phiE"] = {"L2": 1.0}
    with pytest.raises(ProblemError):
        comparison_table(problem, [result])


def test_a_result_missing_its_levels_is_refused_by_name():
    with pytest.raises(ProblemError) as caught:
        comparison_table(load_problem("fda_monodomain"), [{"solver": "a", "problem": "fda_monodomain", "mesh": "hex"}])
    assert caught.value.code == "results_invalid"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("where", ["values", "exact"])
def test_a_non_finite_value_is_refused_not_reported_as_zero_error(bad, where):
    problem = load_problem("fda_monodomain")
    values, exact = [1.0, 2.0, 3.0], [1.0, 2.0, 3.0]
    {"values": values, "exact": exact}[where][1] = bad
    with pytest.raises(ProblemError) as caught:
        error_norms(problem, values, exact, [1.0, 1.0, 1.0])
    assert caught.value.code == "non_finite_values"
