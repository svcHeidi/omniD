"""The shared norm, the order fit and the comparison table, on synthetic grids whose answers are known by hand."""
from __future__ import annotations

import math

import pytest

from omnidriver.verifier.convergence import (
    comparison_table, error_norms, exact_values, observed_orders, orders_against_a_finer_level, temporal_table,
)
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


def _result(problem: dict, solver: str, scale: float, power: float, mesh: str = "hex", dimension: int = 1) -> dict:
    ladder = problem["refinement"][mesh]
    return {
        "solver": solver, "problem": problem["id"], "mesh": mesh, "stated": {"space": 2},
        "levels": [
            {"dimension": dimension, "cells_per_axis": n, "dt": dt, "steps": steps,
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


def test_a_tet_level_is_judged_on_the_tet_ladder_and_only_in_its_dimensions():
    problem = load_problem("fda_monodomain")
    (row,) = comparison_table(problem, [_result(problem, "a", 1.0, 2, mesh="tet", dimension=3)])["rows"]
    assert row["mesh"] == "tet" and row["least_squares_order"]["V"]["L2"] == pytest.approx(2)
    with pytest.raises(ProblemError) as caught:
        comparison_table(problem, [_result(problem, "a", 1.0, 2, mesh="tet", dimension=2)])
    assert "off the problem's tet ladder" in str(caught.value)


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


@pytest.mark.parametrize("bad", [math.nan, math.inf, 0.0, -1e-3])
def test_an_error_that_has_no_logarithm_is_refused_by_name(bad):
    with pytest.raises(ProblemError) as caught:
        observed_orders([0.1, 0.05, 0.025], [1e-2, bad, 1e-4])
    assert caught.value.code == "errors_unusable"


def test_a_spacing_that_repeats_or_is_not_positive_is_refused_by_name():
    for spacings in ([0.1, 0.1], [0.1, 0.0], [0.1, math.nan]):
        with pytest.raises(ProblemError) as caught:
            observed_orders(spacings, [1e-2, 1e-3])
        assert caught.value.code == "spacings_unusable"


def test_one_level_has_no_order():
    assert observed_orders([0.1], [1e-2]) == {"successive": [], "least_squares": None}


def test_a_level_listed_twice_is_refused_by_name():
    problem = load_problem("fda_monodomain")
    result = _result(problem, "a", 1.0, 2)
    result["levels"].append(dict(result["levels"][0]))
    with pytest.raises(ProblemError) as caught:
        comparison_table(problem, [result])
    assert caught.value.code == "results_invalid"
    assert "twice" in str(caught.value)


def test_a_field_present_at_only_some_levels_is_refused_not_dropped():
    problem = load_problem("fda_monodomain")
    result = _result(problem, "a", 1.0, 2)
    for level in result["levels"]:
        level["errors"]["u1"] = dict(level["errors"]["V"])
    del result["levels"][1]["errors"]["u1"]
    with pytest.raises(ProblemError) as caught:
        comparison_table(problem, [result])
    assert caught.value.code == "results_invalid"
    assert "u1" in str(caught.value)


def _temporal(problem: dict, scale: float, power: float, *, reference: str = "exact", dimension: int = 1) -> dict:
    ladder = problem["refinement"]["temporal"]
    rungs = list(zip(ladder["dt"], ladder["steps"]))
    if reference == "finest_dt":
        rungs = rungs[:-1]
    return {
        "solver": "a", "problem": problem["id"], "configuration": "godunov", "reference": reference,
        "stated": {"time": 1},
        "levels": [
            {"dimension": dimension, "cells_per_axis": ladder["cells_per_axis"][str(dimension)], "dt": dt,
             "steps": steps, "errors": {"V": {kind: scale * dt**power for kind in ("L1", "L2", "Linf")}}}
            for dt, steps in rungs
        ],
    }


def test_the_temporal_table_fits_the_order_in_dt_at_a_fixed_mesh():
    problem = load_problem("fda_monodomain")
    table = temporal_table(problem, [_temporal(problem, 3.0, 1), _temporal(problem, 5.0, 2, dimension=2)])
    first, second = table["rows"]
    assert (first["dimension"], first["cells_per_axis"], second["dimension"]) == (1, 640, 2)
    assert first["least_squares_order"]["V"]["L2"] == pytest.approx(1)
    assert second["least_squares_order"]["V"]["Linf"] == pytest.approx(2)
    assert first["levels"][0]["observed_order"]["V"]["L2"] is None
    assert first["levels"][1]["observed_order"]["V"]["L2"] == pytest.approx(1)
    assert first["levels"][0]["time"] == pytest.approx(8 * 0.025)
    assert first["stated"] == {"time": 1} and first["configuration"] == "godunov"


@pytest.mark.parametrize("power", [1, 2])
def test_an_error_against_a_finer_level_has_the_order_of_the_scheme_not_the_naive_ratio(power):
    dts, finest = [0.008, 0.004, 0.002], 0.001
    errors = [3 * (dt**power - finest**power) for dt in dts]
    assert observed_orders(dts, errors)["least_squares"] > power + 0.1
    orders = orders_against_a_finer_level(dts, errors, finest)
    assert orders["successive"] == pytest.approx([power, power], abs=2e-3)
    assert orders["least_squares"] == pytest.approx(power, abs=2e-3)


def test_a_ratio_no_order_in_range_explains_has_no_order():
    orders = orders_against_a_finer_level([0.008, 0.004], [1.0, 1.0], 0.001)
    assert orders["successive"] == [None]
    with pytest.raises(ProblemError) as caught:
        orders_against_a_finer_level([0.008, 0.001], [1.0, 0.5], 0.001)
    assert caught.value.code == "spacings_unusable"


def test_against_the_finest_dt_the_finest_level_is_refused_and_the_rest_are_tabled():
    problem = load_problem("fda_monodomain")
    ladder = problem["refinement"]["temporal"]
    result = _temporal(problem, 1.0, 1, reference="finest_dt")
    for level in result["levels"]:
        level["errors"]["V"] = {kind: level["dt"] - ladder["dt"][-1] for kind in ("L1", "L2", "Linf")}
    (row,) = temporal_table(problem, [result])["rows"]
    assert row["reference"] == "finest_dt" and len(row["levels"]) == len(ladder["dt"]) - 1
    assert row["least_squares_order"]["V"]["L2"] == pytest.approx(1, abs=2e-3)
    with_finest = _temporal(problem, 1.0, 2)
    with_finest["reference"] = "finest_dt"
    with pytest.raises(ProblemError) as caught:
        temporal_table(problem, [with_finest])
    assert caught.value.code == "results_invalid"


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r["levels"][0].__setitem__("cells_per_axis", 320),
        lambda r: r["levels"][0].__setitem__("steps", 9),
        lambda r: r["levels"][0].__setitem__("dimension", 3),
        lambda r: r.__setitem__("reference", "richardson"),
        lambda r: r["levels"].append(dict(r["levels"][0])),
        lambda r: r["levels"][1]["errors"].__setitem__("u1", {"L1": 1.0, "L2": 1.0, "Linf": 1.0}),
        lambda r: r["levels"][1]["errors"]["V"].pop("Linf"),
    ],
)
def test_a_temporal_level_off_the_ladder_or_inconsistent_is_refused_by_name(edit):
    problem = load_problem("fda_monodomain")
    result = _temporal(problem, 1.0, 1)
    edit(result)
    with pytest.raises(ProblemError) as caught:
        temporal_table(problem, [result])
    assert caught.value.code == "results_invalid"


def test_a_problem_without_a_temporal_ladder_has_no_temporal_table():
    problem = load_problem("fda_monodomain")
    del problem["refinement"]["temporal"]
    with pytest.raises(ProblemError):
        temporal_table(problem, [])


def test_the_mesh_table_does_not_take_the_temporal_ladder_for_a_mesh():
    problem = load_problem("fda_monodomain")
    result = _result(problem, "a", 1.0, 2)
    result["mesh"] = "temporal"
    with pytest.raises(ProblemError) as caught:
        comparison_table(problem, [result])
    assert "not in ['hex', 'tet']" in str(caught.value)
