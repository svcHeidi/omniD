"""``omnidriver-verify`` answers and refuses as JSON on stdout."""
from __future__ import annotations

import json

import pytest

from omnidriver.verifier.cli import main
from omnidriver.verifier.convergence import exact_values
from omnidriver.verifier.problem import load_problem


def _run(capsys, *argv: str) -> tuple[int, dict]:
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_problems_lists_each_problem(capsys):
    code, answer = _run(capsys, "problems")
    assert code == 0 and answer["status"] == "ok"
    assert {tuple(sorted(entry)) for entry in answer["problems"]} == {("dimensions", "id", "mesh_progression", "title")}
    assert [entry["id"] for entry in answer["problems"]] == ["anisotropic_monodomain", "fda_monodomain"]


def test_show_prints_the_definition(capsys):
    code, answer = _run(capsys, "show", "fda_monodomain")
    assert code == 0 and answer["status"] == "ok"
    assert answer["problem"] == load_problem("fda_monodomain")


def test_residual_prints_the_verdict_per_dimension(capsys):
    code, answer = _run(capsys, "residual", "fda_monodomain")
    assert code == 0 and answer["status"] == "passed"
    assert [entry["residuals"]["pde"] for entry in answer["dimensions"]] == ["0", "0", "0"]


@pytest.mark.parametrize("argv", [("show", "nope"), ("residual", "nope")])
def test_an_unknown_problem_is_refused(capsys, argv):
    code, answer = _run(capsys, *argv)
    assert code == 1
    assert answer["status"] == "failed" and answer["code"] == "unknown_problem"


def test_a_usage_error_is_refused(capsys):
    code, answer = _run(capsys, "frobnicate")
    assert code == 1 and answer["code"] == "usage"


def test_compare_tables_the_results_files(capsys, tmp_path):
    problem = load_problem("fda_monodomain")
    ladder = problem["refinement"]["hex"]
    result = {
        "solver": "toy", "problem": "fda_monodomain", "mesh": "hex", "stated": {"space": 2},
        "levels": [{"dimension": 1, "cells_per_axis": n, "dt": dt, "steps": steps,
                    "errors": {"V": {"L1": n**-2.0, "L2": n**-2.0, "Linf": n**-2.0}}}
                   for n, dt, steps in zip(ladder["cells_per_axis"], ladder["dt"], ladder["steps"])],
    }
    path = tmp_path / "toy.json"
    path.write_text(json.dumps(result))
    code, answer = _run(capsys, "compare", "fda_monodomain", "--results", str(path))
    assert code == 0 and answer["status"] == "ok"
    [row] = answer["rows"]
    assert row["solver"] == "toy" and row["least_squares_order"]["V"]["L2"] == pytest.approx(2)


def test_compare_temporal_tables_the_temporal_ladder(capsys, tmp_path):
    ladder = load_problem("fda_monodomain")["refinement"]["temporal"]
    result = {
        "solver": "toy", "problem": "fda_monodomain", "configuration": "lie", "reference": "exact",
        "stated": {"time": 1},
        "levels": [{"dimension": 2, "cells_per_axis": 640, "dt": dt, "steps": steps,
                    "errors": {"V": {"L1": dt, "L2": dt, "Linf": dt}}}
                   for dt, steps in zip(ladder["dt"], ladder["steps"])],
    }
    path = tmp_path / "toy.json"
    path.write_text(json.dumps(result))
    code, answer = _run(capsys, "compare", "fda_monodomain", "--temporal", "--results", str(path))
    assert code == 0 and answer["refinement"] == "temporal"
    [row] = answer["rows"]
    assert row["least_squares_order"]["V"]["L2"] == pytest.approx(1)


def test_compare_refuses_an_unreadable_results_file(capsys, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{")
    code, answer = _run(capsys, "compare", "fda_monodomain", "--results", str(path))
    assert code == 1 and answer["code"] == "results_invalid" and str(path) in answer["error"]


def test_residual_prints_the_anisotropic_verdict(capsys):
    code, answer = _run(capsys, "residual", "anisotropic_monodomain")
    assert code == 0 and answer["status"] == "passed"
    assert [entry["dimension"] for entry in answer["dimensions"]] == [3]


def _written(tmp_path, content) -> str:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(content))
    return str(path)


def _generated(problem: dict) -> dict:
    cell = problem["cell_model"]
    given = {"Cm": problem["parameters"]["Cm"], "chi": problem["parameters"]["chi"],
             "Beta": problem["derived"]["Beta"]["native"]}
    return {"rates": dict(cell["rates"]), "Iion": cell["Iion"], "parameters": given}


def test_cell_model_prints_gate_one_on_a_generated_model(capsys, tmp_path):
    model = _generated(load_problem("fda_monodomain"))
    code, answer = _run(capsys, "cell-model", "fda_monodomain", "--model", _written(tmp_path, model))
    assert code == 0 and answer["status"] == "passed"
    model["parameters"].update(Cm=3, chi=2)
    code, answer = _run(capsys, "cell-model", "fda_monodomain", "--model", _written(tmp_path, model))
    assert code == 1 and answer["status"] == "failed"


def test_cell_model_takes_what_the_solvers_pde_was_given(capsys, tmp_path):
    model = {**_generated(load_problem("fda_monodomain")), "pde_parameters": {"Cm": 3, "chi": 2}}
    code, answer = _run(capsys, "cell-model", "fda_monodomain", "--model", _written(tmp_path, model))
    assert code == 1 and answer["status"] == "failed"


def test_cell_model_refuses_input_that_is_not_an_object(capsys, tmp_path):
    code, answer = _run(capsys, "cell-model", "fda_monodomain", "--model", _written(tmp_path, [1]))
    assert code == 1 and answer["code"] == "results_invalid"


def test_norms_of_the_exact_field_are_zero_and_of_a_shifted_one_are_the_shift(capsys, tmp_path):
    problem = load_problem("fda_monodomain")
    points = [[0.0], [0.5], [1.0]]
    exact = exact_values(problem, 1, "V", 0.0, points)
    spec = {"dimension": 1, "field": "V", "time": 0.0, "points": points, "values": exact,
            "weights": {"weight": "nodal_control_volume", "elements": [[0, 1], [1, 2]], "element": "structured"}}
    code, answer = _run(capsys, "norms", "fda_monodomain", "--values", _written(tmp_path, spec))
    assert code == 0 and answer["norms"] == {"L1": 0.0, "L2": 0.0, "Linf": 0.0}
    spec["values"] = [value + 0.25 for value in exact]
    code, answer = _run(capsys, "norms", "fda_monodomain", "--values", _written(tmp_path, spec))
    assert code == 0 and answer["norms"] == pytest.approx({"L1": 0.25, "L2": 0.25, "Linf": 0.25})


def test_norms_weight_a_uniform_grid_by_cell_volume(capsys, tmp_path):
    problem = load_problem("fda_monodomain")
    points = [[0.125], [0.375], [0.625], [0.875]]
    exact = exact_values(problem, 1, "V", 0.0, points)
    spec = {"dimension": 1, "field": "V", "time": 0.0, "points": points,
            "values": [value + e for value, e in zip(exact, (0.4, 0.0, 0.0, 0.0))],
            "weights": {"weight": "cell_volume", "cells_per_axis": 4, "edge": 1.0}}
    code, answer = _run(capsys, "norms", "fda_monodomain", "--values", _written(tmp_path, spec))
    assert code == 0 and answer["norms"] == pytest.approx({"L1": 0.1, "L2": 0.2, "Linf": 0.4})


@pytest.mark.parametrize(("weights", "reported"), [
    ({"weight": "mass"}, "the weights"),
    ({"weight": "cell_volume"}, "the weights"),
    ([1.0], "of one length"),
])
def test_norms_refuse_weights_the_problem_does_not_offer_or_that_do_not_fit(capsys, tmp_path, weights, reported):
    spec = {"dimension": 1, "field": "V", "time": 0.0, "points": [[0.0], [1.0]], "values": [1.0, -1.0],
            "weights": weights}
    code, answer = _run(capsys, "norms", "fda_monodomain", "--values", _written(tmp_path, spec))
    assert code == 1 and reported in answer["error"]
