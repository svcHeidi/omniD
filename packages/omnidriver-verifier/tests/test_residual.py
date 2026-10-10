"""Gate 1: the exact fields solve the problem's own equations, with the source it declares, for every dimension."""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("sympy")

from omnidriver.core.refusal import failure
from omnidriver.verifier.problem import load_problem
from omnidriver.verifier.residual import residual_verdict


def test_the_fda_monodomain_problem_has_zero_residual_in_every_dimension():
    verdict = residual_verdict(load_problem("fda_monodomain"))
    assert verdict["status"] == "passed"
    assert [entry["dimension"] for entry in verdict["dimensions"]] == [1, 2, 3]
    for entry in verdict["dimensions"]:
        assert entry["status"] == "passed"
        assert entry["residuals"] == {"pde": "0", "u1": "0", "u2": "0", "u3": "0"}
        assert entry["source"] == {"derived": "0", "declared": "0"}
        assert set(entry["boundary"].values()) == {"0"}
        assert len(entry["boundary"]) == 2 * entry["dimension"]


def test_the_native_beta_literals_are_reported_against_the_derived_value():
    verdict = residual_verdict(load_problem("fda_monodomain"))
    beta = {entry["dimension"]: entry["derived"]["Beta"] for entry in verdict["dimensions"]}
    assert [beta[d]["native"] for d in (1, 2, 3)] == [-1.1, -5.9, -8.6]
    for d in (1, 2, 3):
        assert abs(beta[d]["value"] - beta[d]["native"]) < 1e-7
        assert beta[d]["difference"] == pytest.approx(beta[d]["native"] - beta[d]["value"])


def test_a_transcription_error_in_a_rate_fails_that_equation_only():
    problem = load_problem("fda_monodomain")
    problem["cell_model"]["rates"]["u2"] = "(u1 + u3 - V)*u2**3"
    verdict = residual_verdict(problem)
    assert verdict["status"] == "failed"
    for entry in verdict["dimensions"]:
        assert entry["status"] == "failed"
        assert entry["residuals"]["u2"] != "0"
        assert entry["residuals"]["pde"] == entry["residuals"]["u1"] == "0"


def test_a_wrong_diffusion_coefficient_shows_as_a_nonzero_source():
    problem = load_problem("fda_monodomain")
    problem["derived"]["Beta"]["expression"]["3"] = "-pi**2*(sigma_xx + 4*sigma_yy)"
    verdict = residual_verdict(problem)
    by_dimension = {entry["dimension"]: entry for entry in verdict["dimensions"]}
    assert by_dimension[1]["status"] == by_dimension[2]["status"] == "passed"
    assert by_dimension[3]["source"]["derived"] != "0"
    assert by_dimension[3]["residuals"]["pde"] != "0"


def test_an_exact_field_with_flux_through_a_face_fails_the_boundary():
    problem = load_problem("fda_monodomain")
    problem["fields"]["F"]["1"] = "sin(pi*x)"
    entry = residual_verdict(problem)["dimensions"][0]
    assert entry["status"] == "failed"
    assert entry["boundary"]["x=0"] != "0"


def test_without_sympy_the_check_is_refused_by_name(monkeypatch):
    monkeypatch.setitem(sys.modules, "sympy", None)
    with pytest.raises(Exception) as caught:
        residual_verdict(load_problem("fda_monodomain"))
    assert failure(caught.value)["code"] == "required_check_unavailable"
