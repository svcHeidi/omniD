"""The shared norm, the order fit and the comparison table, on synthetic grids whose answers are known by hand."""
from __future__ import annotations

import math

import pytest

from omnidriver.verifier.convergence import (
    comparison_table, error_norms, exact_values, floor_contaminated, observed_orders,
    orders_against_a_finer_level, source_values, temporal_table,
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


# V.L2 of the paper-ladder runs (dt 0.025 halved, N = 640), from the comparison table of the temporal study.
CF_SBDF2_BACKWARD_2D = {
    "exact": [4.360236897346161e-04, 1.1130944548673546e-04, 2.7643958181182363e-05, 6.412715007400837e-06,
              1.0742290817422945e-06],
    "finest_dt": [4.3496345849557984e-04, 1.1024780321217073e-04, 2.6581345806189617e-05, 5.348312979997971e-06],
}
OC_SPLIT_O2DT_1D = {
    "exact": [0.44030357264930087, 0.44735868398968276, 0.45103934713634924, 0.452928114442365, 0.45388513163554495],
    "finest_dt": [0.017818783155746754, 0.008568303442293737, 0.0037333624838518462, 0.0012550059898725995],
}


def _recorded(problem: dict, series: dict, reference: str, *, dimension: int = 1, **extra) -> dict:
    ladder = problem["refinement"]["temporal"]
    rungs = list(zip(ladder["dt"], ladder["steps"]))[:len(series[reference])]
    return {
        "solver": "s", "problem": problem["id"], "configuration": "c", "reference": reference, "stated": None,
        "levels": [
            {"dimension": dimension, "cells_per_axis": ladder["cells_per_axis"][str(dimension)], "dt": dt,
             "steps": steps, "errors": {"V": {kind: error for kind in ("L1", "L2", "Linf")}}}
            for (dt, steps), error in zip(rungs, series[reference])
        ],
        **extra,
    }


def _table(series: dict, *references: str, dimension: int = 1) -> dict:
    problem = load_problem("fda_monodomain")
    return temporal_table(problem, [_recorded(problem, series, r, dimension=dimension) for r in references])


def test_a_finest_dt_order_is_marked_when_the_solver_does_not_converge_to_the_exact_solution():
    exact, finest = _table(OC_SPLIT_O2DT_1D, "exact", "finest_dt")["rows"]
    assert exact["converges"] is False and finest["converges_to_reference"] is False
    assert finest["least_squares_order"]["V"]["L2"] == pytest.approx(0.965, abs=0.05)


def test_a_finest_dt_order_is_confirmed_when_the_solver_converges():
    exact, finest = _table(CF_SBDF2_BACKWARD_2D, "exact", "finest_dt", dimension=2)["rows"]
    assert exact["converges"] is True and finest["converges_to_reference"] is True


def test_a_finest_dt_row_without_an_exact_row_has_no_verdict():
    (finest,) = _table(OC_SPLIT_O2DT_1D, "finest_dt")["rows"]
    assert finest["converges_to_reference"] is None


def test_the_reference_dt_is_recorded_in_a_finest_dt_row_only():
    exact, finest = _table(CF_SBDF2_BACKWARD_2D, "exact", "finest_dt", dimension=2)["rows"]
    assert finest["reference_dt"] == min(load_problem("fda_monodomain")["refinement"]["temporal"]["dt"])
    assert exact["reference_dt"] is None


def test_an_error_that_stops_decreasing_does_not_converge_whatever_its_fitted_order():
    series = {"exact": [1.0e-3, 4.0e-4, 1.5e-4, 5.0e-5, 1.0e-3]}
    (row,) = _table(series, "exact")["rows"]
    assert row["converges"] is False


def test_the_last_level_is_flagged_when_its_order_leaves_the_trend_and_the_fit_without_it_is_given():
    (row,) = _table(CF_SBDF2_BACKWARD_2D, "exact", dimension=2)["rows"]
    assert row["floor_contaminated"]["V"]["L2"] is True
    assert row["least_squares_order"]["V"]["L2"] == pytest.approx(2.14, abs=0.01)
    assert row["least_squares_order_without_floor"]["V"]["L2"] == pytest.approx(2.03, abs=0.01)


def test_a_steady_drift_of_the_order_is_a_trend_not_a_floor():
    sbdf2_euler_u1 = [2.820e-04, 8.719e-05, 2.960e-05, 1.123e-05, 4.713e-06]
    problem = load_problem("fda_monodomain")
    orders = observed_orders([0.025 / 2**k for k in range(5)], sbdf2_euler_u1)["successive"]
    assert orders == pytest.approx([1.694, 1.558, 1.398, 1.253], abs=2e-3)
    assert floor_contaminated(sbdf2_euler_u1, orders) is False


def test_an_error_that_does_not_decrease_at_the_last_level_is_floor_contaminated():
    assert floor_contaminated([4e-4, 1e-4, 2.5e-5, 2.6e-5], [2.0, 2.0, -0.04]) is True
    assert floor_contaminated([4e-4, 1e-4], [2.0]) is False


def test_orders_against_a_finer_level_are_refused_unless_the_spacings_decrease():
    with pytest.raises(ProblemError) as caught:
        orders_against_a_finer_level([0.002, 0.004, 0.008], [1.0, 3.0, 7.0], 0.001)
    assert caught.value.code == "spacings_unusable" and "decrease" in str(caught.value)


def test_both_references_round_their_orders_to_the_same_digits():
    dts = [0.025 / 2**k for k in range(5)]
    exact = observed_orders(dts, CF_SBDF2_BACKWARD_2D["exact"])
    finer = orders_against_a_finer_level(dts[:-1], CF_SBDF2_BACKWARD_2D["finest_dt"], dts[-1])
    for orders in (exact, finer):
        assert all(round(order, 3) == order for order in [*orders["successive"], orders["least_squares"]])


@pytest.mark.parametrize("reference, declared", [("finest_dt", 0.003125), ("exact", 0.0015625)])
def test_a_declared_reference_dt_that_contradicts_the_reference_is_refused(reference, declared):
    problem = load_problem("fda_monodomain")
    result = _recorded(problem, CF_SBDF2_BACKWARD_2D, reference, dimension=2, reference_dt=declared)
    with pytest.raises(ProblemError) as caught:
        temporal_table(problem, [result])
    assert caught.value.code == "results_invalid" and "reference_dt" in str(caught.value)


def test_a_declared_reference_dt_that_is_the_ladders_finest_is_accepted():
    problem = load_problem("fda_monodomain")
    result = _recorded(problem, CF_SBDF2_BACKWARD_2D, "finest_dt", dimension=2, reference_dt=0.0015625)
    (row,) = temporal_table(problem, [result])["rows"]
    assert row["reference_dt"] == 0.0015625


def test_the_declared_source_is_evaluated_from_the_problems_expression():
    anisotropic = load_problem("anisotropic_monodomain")
    x, y, z, t = 0.3, 0.4, 0.5, 0.2
    p = anisotropic["parameters"]
    s = [math.sin(math.pi * v) ** 2 for v in (x, y, z)]
    d = [math.pi * math.sin(2 * math.pi * v) for v in (x, y, z)]
    dd = [2 * math.pi**2 * math.cos(2 * math.pi * v) for v in (x, y, z)]
    divergence = (p["sigma_xx"] * dd[0] * s[1] * s[2] + p["sigma_yy"] * s[0] * dd[1] * s[2]
                  + p["sigma_zz"] * s[0] * s[1] * dd[2] + 2 * p["sigma_xy"] * d[0] * d[1] * s[2]
                  + 2 * p["sigma_xz"] * d[0] * s[1] * d[2] + 2 * p["sigma_yz"] * s[0] * d[1] * d[2])
    expected = math.sqrt(1 + t) * (p["Beta"] * s[0] * s[1] * s[2] - divergence)
    assert source_values(anisotropic, 3, t, [(x, y, z)]) == pytest.approx([expected], rel=1e-14)
    assert source_values(load_problem("fda_monodomain"), 2, t, [(x, y)]) == [0]


def test_a_source_in_a_dimension_the_problem_lacks_is_refused():
    with pytest.raises(ProblemError):
        source_values(load_problem("anisotropic_monodomain"), 2, 0.0, [(0.5, 0.5)])


def test_the_anisotropic_ladder_is_three_dimensional_only():
    problem = load_problem("anisotropic_monodomain")
    ladder = problem["refinement"]["hex"]
    levels = [{"dimension": 3, "cells_per_axis": n, "dt": dt, "steps": steps,
               "errors": {"V": {"L1": e, "L2": e, "Linf": e}}}
              for n, dt, steps, e in zip(ladder["cells_per_axis"], ladder["dt"], ladder["steps"],
                                         [1e-2, 2.5e-3, 6.25e-4, 1.5625e-4])]
    (row,) = comparison_table(problem, [{"solver": "toy", "problem": "anisotropic_monodomain", "mesh": "hex",
                                         "levels": levels}])["rows"]
    assert row["dimension"] == 3 and row["least_squares_order"]["V"]["L2"] == pytest.approx(2.0, abs=1e-3)
    with pytest.raises(ProblemError):
        comparison_table(problem, [{"solver": "toy", "problem": "anisotropic_monodomain", "mesh": "hex",
                                    "levels": [{**levels[0], "dimension": 2}]}])


def test_a_field_the_expression_does_not_name_is_not_evaluated():
    problem = load_problem("anisotropic_monodomain")
    problem["fields"]["LF"]["3"] = "1/0"
    assert exact_values(problem, 3, "V", 0.0, [(0.5, 0.5, 0.5)]) == pytest.approx([1.0])
    with pytest.raises(ZeroDivisionError):
        source_values(problem, 3, 0.0, [(0.5, 0.5, 0.5)])
