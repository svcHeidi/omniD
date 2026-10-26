"""Gate 1: the exact fields solve the problem's own equations, with the source it declares, for every dimension."""
from __future__ import annotations

import copy
import sys

import pytest
import sympy  # noqa: F401  a missing [symbolic] extra must fail these tests, not skip them

from omnidriver.core.refusal import failure
from omnidriver.verifier.problem import ProblemError, load_problem
from omnidriver.verifier.residual import cell_model_verdict, residual_verdict


def test_the_fda_monodomain_problem_has_zero_residual_in_every_dimension():
    verdict = residual_verdict(load_problem("fda_monodomain"))
    assert verdict["status"] == "passed"
    assert [entry["dimension"] for entry in verdict["dimensions"]] == [1, 2, 3]
    for entry in verdict["dimensions"]:
        assert entry["status"] == "passed"
        assert entry["residuals"] == {"pde": "0", "u1": "0", "u2": "0", "u3": "0"}
        assert set(entry["initial"]) == {"V", "u1", "u2", "u3"}
        assert entry["source"] == {"derived": "0", "declared": "0"}
        assert set(entry["boundary"].values()) == {"0"}
        assert len(entry["boundary"]) == 2 * entry["dimension"]


def test_a_native_literal_within_the_stated_tolerance_passes_and_is_reported():
    problem = load_problem("fda_monodomain")
    tolerance = problem["derived"]["Beta"]["tolerance"]
    for entry in residual_verdict(problem)["dimensions"]:
        beta = entry["derived"]["Beta"]
        assert beta["status"] == "passed"
        assert abs(beta["difference"]) <= tolerance
        assert beta["difference"] == pytest.approx(beta["native"] - beta["value"])


def test_a_wrong_conductivity_fails_the_native_literal():
    problem = load_problem("fda_monodomain")
    problem["parameters"]["sigma_xx"] *= 2
    verdict = residual_verdict(problem)
    assert verdict["status"] == "failed"
    for entry in verdict["dimensions"]:
        assert entry["status"] == "failed"
        assert entry["derived"]["Beta"]["status"] == "failed"


def test_a_conductivity_rounded_to_six_digits_fails_the_native_literal():
    problem = load_problem("fda_monodomain")
    problem["parameters"].update(sigma_xx=0.111453, sigma_yy=0.121585, sigma_zz=0.0303964)
    by_dimension = {entry["dimension"]: entry for entry in residual_verdict(problem)["dimensions"]}
    assert by_dimension[3]["derived"]["Beta"]["status"] == "failed"


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


def test_the_residual_reads_the_equation_from_the_data():
    problem = load_problem("fda_monodomain")
    problem["pde"]["equation"] = "chi*Cm*Derivative(V, t) + Iion - div(sigma*grad(V)) = source"
    verdict = residual_verdict(problem)
    assert verdict["status"] == "failed"
    assert all(entry["residuals"]["pde"] != "0" for entry in verdict["dimensions"])


def test_the_initial_fields_are_the_exact_fields_at_the_start():
    problem = load_problem("fda_monodomain")
    problem["time"]["start"] = 3
    entry = residual_verdict(problem)["dimensions"][0]
    assert entry["initial"]["u3"] == "0"
    assert entry["initial"]["V"] == "2*cos(pi*x)"


def _generated(problem: dict, **values) -> dict:
    """A cell model as an injection would generate it: the problem's expressions with its own parameter values."""
    cell = problem["cell_model"]
    given = {"Cm": problem["parameters"]["Cm"], "chi": problem["parameters"]["chi"],
             "Beta": problem["derived"]["Beta"]["native"], **values}
    return {"rates": dict(cell["rates"]), "Iion": cell["Iion"], "parameters": given}


def test_a_generated_cell_model_with_the_pde_pair_passes():
    problem = load_problem("fda_monodomain")
    verdict = cell_model_verdict(problem, _generated(problem))
    assert verdict["status"] == "passed"
    assert all(entry["residuals"]["pde"] == "0" for entry in verdict["dimensions"])


def test_a_generated_cell_model_with_the_pair_swapped_is_caught():
    problem = load_problem("fda_monodomain")
    verdict = cell_model_verdict(problem, _generated(problem, Cm=3, chi=2))
    assert verdict["status"] == "failed"
    for entry in verdict["dimensions"]:
        assert entry["residuals"]["pde"] != "0"
        assert entry["parameters"]["Cm"] == {"problem": 2, "pde": 2, "cell_model": 3, "status": "failed"}


def test_a_pde_given_the_pair_swapped_is_caught():
    problem = load_problem("fda_monodomain")
    verdict = cell_model_verdict(problem, _generated(problem), pde_parameters={"Cm": 3, "chi": 2})
    assert verdict["status"] == "failed"
    for entry in verdict["dimensions"]:
        assert entry["residuals"]["pde"] != "0"
        assert entry["parameters"]["chi"]["status"] == "failed"


def test_a_generated_current_per_unit_capacitance_is_caught():
    problem = load_problem("fda_monodomain")
    model = _generated(problem)
    model["Iion"] = f"({model['Iion']})/Cm"
    verdict = cell_model_verdict(problem, model)
    assert verdict["status"] == "failed"
    assert all(entry["residuals"]["pde"] != "0" for entry in verdict["dimensions"])


def test_a_generated_beta_off_its_derived_value_is_caught():
    problem = load_problem("fda_monodomain")
    verdict = cell_model_verdict(problem, _generated(problem, Beta={"1": -1.1, "2": -5.9, "3": -8.7}))
    by_dimension = {entry["dimension"]: entry for entry in verdict["dimensions"]}
    assert by_dimension[2]["status"] == "passed"
    assert by_dimension[3]["derived"]["Beta"]["status"] == "failed"


def test_a_generated_cell_model_naming_a_parameter_it_gives_no_value_is_refused():
    problem = load_problem("fda_monodomain")
    model = _generated(problem)
    del model["parameters"]["chi"]
    with pytest.raises(ProblemError) as caught:
        cell_model_verdict(problem, model)
    assert "cell_model.parameters" in str(caught.value)


def test_a_box_below_zero_gives_its_coordinates_no_sign():
    problem = load_problem("fda_monodomain")
    problem["domain"]["box"] = [[-1, 1], [0, 1], [0, 1]]
    entry = residual_verdict(problem)["dimensions"][0]
    assert entry["residuals"] == {"pde": "0", "u1": "0", "u2": "0", "u3": "0"}
    assert set(entry["boundary"]) == {"x=-1", "x=1"}


def _fixed_capacitance(problem: dict, iion: str) -> dict:
    """A cell model generated for a solver whose Cm is fixed at 1: the problem's own parameter values, and ``iion``."""
    return {**_generated(problem), "Iion": iion}


def test_a_model_mapped_to_a_fixed_capacitance_passes():
    problem = load_problem("fda_monodomain")
    model = _fixed_capacitance(problem, f"({problem['cell_model']['Iion']})*1/Cm")
    verdict = cell_model_verdict(problem, model, pde_parameters={"Cm": 1, "chi": 6}, fixed_capacitance=1)
    assert verdict["status"] == "passed"
    for entry in verdict["dimensions"]:
        assert entry["residuals"]["pde"] == "0"
        assert entry["parameters"]["chi"] == {"problem": 3, "pde": 6, "mapped": 6, "cell_model": 3,
                                              "status": "passed"}
        assert entry["fixed_capacitance"]["status"] == "passed"


def test_a_mapping_that_forgets_the_current_scaling_fails():
    problem = load_problem("fda_monodomain")
    model = _fixed_capacitance(problem, problem["cell_model"]["Iion"])
    verdict = cell_model_verdict(problem, model, pde_parameters={"Cm": 1, "chi": 6}, fixed_capacitance=1)
    assert verdict["status"] == "failed"
    assert all(entry["residuals"]["pde"] != "0" for entry in verdict["dimensions"])


def test_a_pde_given_the_unmapped_chi_under_a_fixed_capacitance_fails():
    problem = load_problem("fda_monodomain")
    model = _fixed_capacitance(problem, f"({problem['cell_model']['Iion']})/Cm")
    verdict = cell_model_verdict(problem, model, pde_parameters={"Cm": 1, "chi": 3}, fixed_capacitance=1)
    assert verdict["status"] == "failed"
    for entry in verdict["dimensions"]:
        assert entry["parameters"]["chi"]["status"] == "failed"


def test_the_mapping_is_read_from_the_problem_data():
    problem = load_problem("fda_monodomain")
    problem["units"]["fixed_capacitance"]["maps"]["chi"] = "chi*Cm"
    model = _fixed_capacitance(problem, f"({problem['cell_model']['Iion']})/Cm")
    verdict = cell_model_verdict(problem, model, pde_parameters={"Cm": 1, "chi": 6}, fixed_capacitance=0.5)
    for entry in verdict["dimensions"]:
        assert entry["fixed_capacitance"]["status"] == "failed"
        assert entry["parameters"]["chi"]["mapped"] == 6


def test_the_anisotropic_problem_has_zero_residual_with_a_nonzero_source():
    verdict = residual_verdict(load_problem("anisotropic_monodomain"))
    assert verdict["status"] == "passed"
    (entry,) = verdict["dimensions"]
    assert entry["residuals"] == {"pde": "0", "u1": "0", "u2": "0", "u3": "0"}
    assert entry["source"]["derived"] != "0" and entry["source"]["declared"] != "0"
    assert set(entry["boundary"].values()) == {"0"} and len(entry["boundary"]) == 6
    assert {name for name in entry["parameters"]} >= {"sigma_xy", "sigma_xz", "sigma_yz"}


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("2*sigma_xy*pi*sin(2*pi*x)", "sigma_xy*pi*sin(2*pi*x)"),
        ("2*sigma_xz*pi*sin(2*pi*x)", "2*sigma_yz*pi*sin(2*pi*x)"),
        ("sigma_yy*sin(pi*x)**2*2*pi**2*cos(2*pi*y)", "sigma_yy*sin(pi*x)**2*pi**2*cos(2*pi*y)"),
    ],
)
def test_a_transcription_error_in_the_hessian_shows_as_a_source_difference(old, new):
    problem = load_problem("anisotropic_monodomain")
    text = problem["fields"]["LF"]["3"]
    assert old in text
    problem["fields"]["LF"]["3"] = text.replace(old, new, 1)
    verdict = residual_verdict(problem)
    assert verdict["status"] == "failed"
    assert verdict["dimensions"][0]["residuals"]["pde"] != "0"
    assert {key: value for key, value in verdict["dimensions"][0]["residuals"].items() if key != "pde"} == {
        "u1": "0", "u2": "0", "u3": "0"}


def test_the_ionic_coefficient_beta_is_free_because_the_source_absorbs_it():
    problem = load_problem("anisotropic_monodomain")
    problem["parameters"]["Beta"] = -5.9
    assert residual_verdict(problem)["status"] == "passed"


def test_a_source_that_leaves_out_the_ionic_coefficient_term_fails():
    problem = load_problem("anisotropic_monodomain")
    problem["source"]["expression"] = "sqrt(1 + t)*(-LF)"
    assert residual_verdict(problem)["status"] == "failed"


def test_a_face_with_flux_fails_the_anisotropic_boundary():
    problem = load_problem("anisotropic_monodomain")
    problem["fields"]["F"]["3"] = "sin(pi*x)**2*sin(pi*y)**2*sin(pi*z)"
    verdict = residual_verdict(problem)
    assert verdict["dimensions"][0]["boundary"]["z=0"] != "0"


def _source_in_the_current(problem: dict, carried: str) -> tuple[dict, dict]:
    """A solver with no source term, as an injection would carry it: the source is a per-node amplitude state Sa
    (Beta*F - LF, constant in time) times sqrt(1 + t) in a current mapped to Cm_s = 1, judged against the problem with
    its source moved into the cell model."""
    candidate = copy.deepcopy(problem)
    candidate["cell_model"]["states"] = [*problem["cell_model"]["states"], "Sa"]
    candidate["cell_model"]["rates"]["Sa"] = "0"
    candidate["exact"]["Sa"] = "Beta*F - LF"
    candidate["source"]["expression"] = "0"
    cell = problem["cell_model"]
    model = {"rates": {**cell["rates"], "Sa": "0"}, "Iion": f"({cell['Iion']})*1/Cm - {carried}",
             "parameters": {name: problem["parameters"][name] for name in cell["parameters"]}}
    return candidate, model


def test_a_source_carried_in_the_current_as_amplitude_times_time_factor_passes():
    candidate, model = _source_in_the_current(load_problem("anisotropic_monodomain"), "Sa*sqrt(t + 1)/(chi*Cm/1)")
    verdict = cell_model_verdict(candidate, model, pde_parameters={"Cm": 1, "chi": 6}, fixed_capacitance=1)
    assert verdict["status"] == "passed"
    assert verdict["dimensions"][0]["residuals"] == {"pde": "0", "u1": "0", "u2": "0", "u3": "0", "Sa": "0"}


@pytest.mark.parametrize("carried", ["Sa*sqrt(t + 1)/chi", "Sa*(t + 1)/(chi*Cm/1)", "Sa/(chi*Cm/1)", "-Sa*sqrt(t + 1)/(chi*Cm/1)"])
def test_a_carried_source_with_a_wrong_scale_time_factor_or_sign_fails(carried):
    candidate, model = _source_in_the_current(load_problem("anisotropic_monodomain"), carried)
    verdict = cell_model_verdict(candidate, model, pde_parameters={"Cm": 1, "chi": 6}, fixed_capacitance=1)
    assert verdict["status"] == "failed"
    assert verdict["dimensions"][0]["residuals"]["pde"] != "0"
