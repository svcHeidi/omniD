"""What the supplied C++ requires of electroProperties, as the catalogue's relations judge a case."""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.cardiacfoam.validation import infer_virtual_presence
from omnidriver.openfoam.case_rules import rule_diagnostics

ENTRIES = tuple(entry for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values() for entry in group)
PURKINJE = "conductionNetworkDomains.net.purkinjeGraphModelCoeffs"


def _missing(context: dict) -> set[str]:
    context = dict(context)
    infer_virtual_presence(context)
    return {item.field for item in rule_diagnostics(ENTRIES, context, document="constant/electroProperties")}


def test_max_steps_is_optional_because_ode_solver_defaults_it() -> None:
    entry = next(entry for entry in ENTRIES if entry.driver_path == "$ELECTRO_MODEL_COEFFS.maxSteps")
    assert not entry.required and not entry.required_when
    assert "maxSteps" not in _missing({"myocardiumSolver": "monodomainSolver", "ionicModel": "BuenoOrovio"})


@pytest.mark.parametrize(
    ("ionic", "tension", "needs_solver"),
    [
        ("BuenoOrovio", None, True),
        ("BuenoOroviocompactBatched", None, False),
        ("BuenoOroviocompactBatched", "NashPanfilov", True),
        ("BuenoOroviocompactBatched", "LandNiedererTWorld", True),
        ("BuenoOroviocompactBatched", "LandNiedererBatched", False),
    ],
)
def test_solver_is_required_wherever_an_ode_solver_is_built(ionic: str, tension: str | None, needs_solver: bool) -> None:
    context = {"myocardiumSolver": "monodomainSolver", "ionicModel": ionic, **({"activeTensionModel": tension} if tension else {})}
    assert ("solver" in _missing(context)) is needs_solver


def test_a_gradient_axis_must_name_its_field() -> None:
    context = {
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "BuenoOrovio",
        "ionicHeterogeneity.gradientAxes.apicobasal.beta": 2.0,
    }
    assert "ionicHeterogeneity.gradientAxes.apicobasal.field" in _missing(context)


def test_the_fda_bidomain_verifier_requires_its_reference_point() -> None:
    context = {"myocardiumSolver": "bidomainSolver", "verificationModel.type": "manufacturedFDABidomainVerifier"}
    assert "phiERefPoint" in _missing(context)
    assert "phiERefPoint" not in _missing({"myocardiumSolver": "bidomainSolver"})


@pytest.mark.parametrize(
    ("selector", "needs_ionic_model"),
    [
        ({}, True),
        ({f"{PURKINJE}.conductionSystemSolver": "monodomain1DSolver"}, True),
        ({f"{PURKINJE}.conductionSystemSolver": "eikonalSolver1D"}, False),
    ],
)
def test_a_purkinje_block_without_a_solver_runs_the_default_one_and_needs_its_ionic_model(
    selector: dict, needs_ionic_model: bool,
) -> None:
    context = {"myocardiumSolver": "monodomainSolver", f"{PURKINJE}.chi": 1.0, **selector}
    assert (f"{PURKINJE}.ionicModel" in _missing(context)) is needs_ionic_model


@pytest.mark.parametrize(("ionic", "needs_solver"), [("Stewart", True), ("StewartcompactBatched", False)])
def test_a_purkinje_solver_is_required_only_where_the_ionic_model_builds_an_ode_solver(ionic: str, needs_solver: bool) -> None:
    context = {"myocardiumSolver": "monodomainSolver", f"{PURKINJE}.ionicModel": ionic}
    assert (f"{PURKINJE}.solver" in _missing(context)) is needs_solver


@pytest.mark.parametrize(("ionic", "needs_solver"), [("BuenoOrovio", True), ("BuenoOroviocompactBatched", False)])
def test_a_personalized_template_solver_is_required_only_where_the_ionic_model_builds_an_ode_solver(ionic: str, needs_solver: bool) -> None:
    prefix = "ecgDomains.ecg.personalizedTemplates.ionicModelConfig"
    context = {"myocardiumSolver": "monodomainSolver", "ecgDomains.ecg.ecgSolver": "eikonalECG", f"{prefix}.ionicModel": ionic}
    assert (f"{prefix}.solver" in _missing(context)) is needs_solver
