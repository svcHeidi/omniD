"""``omnidriver-verify`` answers and refuses as JSON on stdout."""
from __future__ import annotations

import json

import pytest

from omnidriver.verifier.cli import main
from omnidriver.verifier.problem import load_problem


def _run(capsys, *argv: str) -> tuple[int, dict]:
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_problems_lists_each_problem(capsys):
    code, answer = _run(capsys, "problems")
    assert code == 0 and answer["status"] == "ok"
    assert [sorted(entry) for entry in answer["problems"]] == [["dimensions", "id", "mesh_progression", "title"]]
    assert [entry["id"] for entry in answer["problems"]] == ["fda_monodomain"]


def test_show_prints_the_definition(capsys):
    code, answer = _run(capsys, "show", "fda_monodomain")
    assert code == 0 and answer["status"] == "ok"
    assert answer["problem"] == load_problem("fda_monodomain")


def test_residual_prints_the_verdict_per_dimension(capsys):
    pytest.importorskip("sympy")
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
