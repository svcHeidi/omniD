"""The problem library loads its shipped problems and refuses a malformed one by name."""
from __future__ import annotations

import tomllib
from importlib.resources import files

import pytest

from omnidriver.core.refusal import failure
from omnidriver.verifier.problem import ProblemError, load_problem, problem_ids, tensor_layout, validate_problem


def _shipped() -> dict:
    return tomllib.loads(files("omnidriver.verifier").joinpath("problems/fda_monodomain.toml").read_text())


def test_the_library_holds_the_fda_and_the_anisotropic_monodomain_problems():
    assert problem_ids() == ["anisotropic_monodomain", "fda_monodomain"]
    for problem_id in problem_ids():
        assert load_problem(problem_id)["id"] == problem_id


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


@pytest.mark.parametrize("problem_id", ["fda_monodomain", "anisotropic_monodomain"])
@pytest.mark.parametrize("mesh", ["hex", "tet", "temporal"])
def test_each_level_is_judged_at_its_report_step(problem_id, mesh):
    problem = load_problem(problem_id)
    ladder = problem["refinement"][mesh]
    for steps, dt in zip(ladder["steps"], ladder["dt"]):
        assert steps * dt + dt / 2 >= problem["time"]["end"] > (steps - 1) * dt + dt / 2


@pytest.mark.parametrize(
    ("edit", "reported"),
    [
        (lambda p: p["refinement"]["hex"]["steps"].__setitem__(0, 23), "refinement.hex.steps"),
        (lambda p: p["refinement"]["hex"]["steps"].pop(), "refinement.hex"),
        (lambda p: p["refinement"]["hex"].update(dt=[0.00892857, 0.00224215, 0.000560538, 0.0003],
                                                 steps=[22, 89, 357, 667]), "refinement.hex.dt_scales_as"),
        (lambda p: p["refinement"]["tet"]["steps"].__setitem__(3, 1428), "refinement.tet.steps"),
        (lambda p: p["refinement"]["tet"].__setitem__("dimensions", [3, 4]), "refinement.tet.dimensions"),
        (lambda p: p["refinement"]["tet"].__setitem__("dimensions", []), "refinement.tet.dimensions"),
        (lambda p: p["refinement"].pop("tet"), "refinement"),
        (lambda p: p.__setitem__("mesh_progression", ["hex", "prism"]), "mesh_progression"),
        (lambda p: p["refinement"]["temporal"]["steps"].__setitem__(0, 9), "refinement.temporal.steps"),
        (lambda p: p["refinement"]["temporal"].update(dt=[0.0125, 0.025], steps=[16, 8]), "refinement.temporal.dt"),
        (lambda p: p["refinement"]["temporal"].update(dt=[0.025], steps=[8]), "refinement.temporal"),
        (lambda p: p["refinement"]["temporal"].__setitem__("mesh", "prism"), "refinement.temporal.mesh"),
        (lambda p: p["refinement"]["temporal"].__setitem__("dimensions", [1, 4]), "refinement.temporal.dimensions"),
        (lambda p: p["refinement"]["temporal"]["cells_per_axis"].pop("2"), "refinement.temporal.cells_per_axis"),
        (lambda p: p["refinement"]["temporal"]["cells_per_axis"].__setitem__("1", 0),
         "refinement.temporal.cells_per_axis"),
        (lambda p: p["refinement"]["temporal"].pop("steps"), "refinement.temporal.steps"),
        (lambda p: p["refinement"]["temporal"].__setitem__("order", 1), "refinement.temporal.order"),
        (lambda p: p["refinement"]["temporal"]["excluded"]["3"].__setitem__("reason", ""),
         "refinement.temporal.excluded.3.reason"),
        (lambda p: p["refinement"]["temporal"]["excluded"].__setitem__("2", {"cells_per_axis": 640, "dt": [0.001],
                                                                             "reason": "r"}),
         "refinement.temporal.excluded.2"),
        (lambda p: p["refinement"]["temporal"]["excluded"]["3"].__setitem__("dt", []),
         "refinement.temporal.excluded.3.dt"),
        (lambda p: p["time"].__setitem__("report_when", "t >= end + 1"), "time.report_when"),
        (lambda p: p["refinement"]["hex"].__setitem__("dt_scales_as", "h**3"), "refinement.hex.dt_scales_as"),
        (lambda p: p["time"].__setitem__("report_when", "t + dt/2"), "time.report_when"),
        (lambda p: p["time"].__setitem__("report_when", "t + tau >= end"), "tau"),
        (lambda p: p["norms"].__setitem__("at", "end"), "norms.at"),
        (lambda p: p["norms"].__setitem__("points", "faces"), "norms.points"),
        (lambda p: p["norms"].__setitem__("weight", "none"), "norms.weight"),
        (lambda p: p["norms"].__setitem__("normalised_by", "cell_count"), "norms.normalised_by"),
        (lambda p: p["norms"].__setitem__("kinds", ["L1", "H1"]), "norms.kinds"),
        (lambda p: p["norms"].__setitem__("fields", ["V", "w"]), "norms.fields"),
    ],
)
def test_the_time_rule_ladder_and_norms_are_checked(edit, reported):
    problem = _shipped()
    edit(problem)
    assert reported in _refused(problem)


def test_the_temporal_ladder_is_optional_and_carries_no_excluded_dimension_by_default():
    problem = _shipped()
    del problem["refinement"]["temporal"]["excluded"]
    validate_problem(problem)
    del problem["refinement"]["temporal"]
    validate_problem(problem)


def test_a_fixed_capacitance_mapping_that_maps_no_current_or_a_stray_name_is_refused():
    problem = _shipped()
    del problem["units"]["fixed_capacitance"]["maps"]["Iion"]
    assert "units.fixed_capacitance.maps" in _refused(problem)
    problem = _shipped()
    problem["units"]["fixed_capacitance"]["maps"]["chi"] = "chi*Cm/C_s"
    assert "C_s" in _refused(problem)


def test_a_symmetric_tensor_names_the_six_upper_entries_by_rows():
    problem = load_problem("anisotropic_monodomain")
    names = problem["pde"]["tensors"]["sigma"]["symmetric"]
    assert names == ["sigma_xx", "sigma_xy", "sigma_xz", "sigma_yy", "sigma_yz", "sigma_zz"]
    assert tensor_layout(problem["pde"]["tensors"]["sigma"], 3) == [
        ["sigma_xx", "sigma_xy", "sigma_xz"], ["sigma_xy", "sigma_yy", "sigma_yz"], ["sigma_xz", "sigma_yz", "sigma_zz"]]
    assert tensor_layout({"diagonal": ["a", "b"]}, 2) == [["a", None], [None, "b"]]


@pytest.mark.parametrize(
    "entries", [["sigma_xx", "sigma_xy", "sigma_xz", "sigma_yy", "sigma_yz"],
                ["sigma_xx", "sigma_xy", "sigma_xz", "sigma_yy", "sigma_yz", "sigma_qq"]])
def test_a_symmetric_tensor_of_the_wrong_size_or_naming_a_stranger_is_refused(entries):
    problem = tomllib.loads(files("omnidriver.verifier").joinpath("problems/anisotropic_monodomain.toml").read_text())
    problem["pde"]["tensors"]["sigma"]["symmetric"] = entries
    assert "pde.tensors.sigma" in _refused(problem)


def test_a_tensor_of_an_unknown_kind_is_refused():
    problem = _shipped()
    problem["pde"]["tensors"]["sigma"] = {"full": ["sigma_xx", "sigma_yy", "sigma_zz"]}
    assert "pde.tensors.sigma" in _refused(problem)


def test_a_finer_temporal_mesh_must_be_finer_than_the_ladders():
    problem = load_problem("anisotropic_monodomain")
    validate_problem(problem)
    problem["refinement"]["temporal"]["finer_cells_per_axis"] = {"3": 40}
    assert "finer_cells_per_axis" in _refused(problem)


def test_the_temporal_ladders_steps_reach_the_end_time_at_every_dt():
    problem = load_problem("fda_monodomain")
    ladder = problem["refinement"]["temporal"]
    assert all(steps * dt == pytest.approx(problem["time"]["end"]) for dt, steps in zip(ladder["dt"], ladder["steps"]))
