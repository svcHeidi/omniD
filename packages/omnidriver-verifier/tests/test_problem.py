"""The problem library loads its shipped problems and refuses a malformed one by name."""
from __future__ import annotations

import tomllib
from importlib.resources import files

import pytest

from omnidriver.core.refusal import failure
from omnidriver.verifier.problem import ProblemError, load_problem, problem_ids, validate_problem


def _shipped() -> dict:
    return tomllib.loads(files("omnidriver.verifier").joinpath("problems/fda_monodomain.toml").read_text())


def test_the_library_holds_the_fda_monodomain_problem():
    assert problem_ids() == ["fda_monodomain"]
    problem = load_problem("fda_monodomain")
    assert problem["dimensions"] == [1, 2, 3]
    assert problem["mesh_progression"] == ["hex"]


def test_an_unknown_id_is_refused_by_name():
    with pytest.raises(ProblemError) as caught:
        load_problem("nope")
    assert failure(caught.value)["code"] == "unknown_problem"


def _refused(problem: dict) -> str:
    with pytest.raises(ProblemError) as caught:
        validate_problem(problem)
    assert caught.value.code == "problem_invalid"
    return str(caught.value)


def test_an_unknown_key_is_refused():
    problem = _shipped()
    problem["colour"] = "red"
    assert "colour" in _refused(problem)
    problem = _shipped()
    problem["cell_model"]["colour"] = "red"
    assert "cell_model.colour" in _refused(problem)


def test_a_missing_block_is_refused():
    problem = _shipped()
    del problem["exact"]
    assert "exact" in _refused(problem)


def test_an_expression_that_does_not_parse_is_refused():
    problem = _shipped()
    problem["exact"]["V"] = "sqrt(1 + t)*"
    assert "exact.V" in _refused(problem)


def test_an_expression_naming_an_unknown_symbol_is_refused():
    problem = _shipped()
    problem["cell_model"]["Iion"] = "Gamma*V"
    assert "Gamma" in _refused(problem)


def test_a_dimension_without_its_field_is_refused():
    problem = _shipped()
    del problem["fields"]["F"]["3"]
    assert "fields.F" in _refused(problem)


def test_a_refinement_with_unequal_ladders_is_refused():
    problem = _shipped()
    problem["refinement"]["hex"]["dt"].pop()
    assert "refinement.hex" in _refused(problem)


def test_a_block_without_provenance_is_refused():
    problem = _shipped()
    del problem["provenance"]["cell_model"]
    assert "cell_model" in _refused(problem)


def test_a_parameter_the_equation_names_is_required():
    problem = _shipped()
    del problem["parameters"]["chi"]
    assert "chi" in _refused(problem)


@pytest.mark.parametrize(("key", "value"), [("use", "average"), ("tolerance", 0), ("tolerance_reason", "")])
def test_a_derived_constant_states_which_value_a_solver_uses_and_its_tolerance(key, value):
    problem = _shipped()
    problem["derived"]["Beta"][key] = value
    assert f"derived.Beta.{key}" in _refused(problem)


@pytest.mark.parametrize(
    ("block", "key", "value", "reported"),
    [
        ("pde", "equation", "chi*(Cm*Derivative(V, t) + Iion) - div(kappa*grad(V)) = source", "kappa"),
        ("pde", "equation", "chi*(Cm*Derivative(V, t) + Iion) - div(sigma*grad(V))", "pde.equation"),
        ("pde", "equation", "chi*(Cm*Derivative(V, t) + Iion) = div(sigma*grad(V))", "pde.equation"),
        ("pde", "parameters", ["Cm", "chi"], "pde.parameters"),
        ("pde", "unknown", "u1", "pde.unknown"),
        ("cell_model", "inputs", ["u1"], "cell_model.inputs"),
        ("cell_model", "parameters", ["Cm", "Beta"], "cell_model.parameters"),
        ("cell_model", "shares_with_pde", ["Cm", "Beta"], "cell_model.shares_with_pde"),
        ("units", "Iion", "per_unit_volume", "units.Iion"),
        ("units", "system", "SI", "units.system"),
        ("domain", "dimension_d_uses", "last_d_intervals", "domain.dimension_d_uses"),
        ("initial", "points", {"cardiacfoam": "vertices"}, "initial.points"),
    ],
)
def test_the_self_description_is_checked(block, key, value, reported):
    problem = _shipped()
    problem[block][key] = value
    assert reported in _refused(problem)


def test_a_diagonal_tensor_names_parameters():
    problem = _shipped()
    problem["pde"]["tensors"]["sigma"]["diagonal"] = ["sigma_xx", "sigma_yy", "sigma_qq"]
    assert "pde.tensors.sigma" in _refused(problem)
