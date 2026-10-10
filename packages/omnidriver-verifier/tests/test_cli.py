"""``omnidriver-verify`` answers and refuses as JSON on stdout."""
from __future__ import annotations

import json

import pytest

from omnidriver.verifier.cli import main


def _run(capsys, *argv: str) -> tuple[int, dict]:
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def test_problems_lists_each_problem(capsys):
    code, answer = _run(capsys, "problems")
    assert code == 0
    assert answer == {"status": "ok", "problems": [{
        "id": "fda_monodomain",
        "title": "Monodomain manufactured solution of Pathmanathan & Gray (FDA RST24CV03.01)",
        "dimensions": [1, 2, 3],
        "mesh_progression": ["hex"],
    }]}


def test_show_prints_the_definition(capsys):
    code, answer = _run(capsys, "show", "fda_monodomain")
    assert code == 0 and answer["status"] == "ok"
    assert answer["problem"]["exact"]["V"] == "sqrt(1 + t)*F"
    assert answer["problem"]["native"]["cardiacfoam"]["commit"].startswith("277dfeb1")


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
