"""The catalogue's rules and cardiacFOAM's cross-field rules, run on the resolved
case of the real native records before anything executes: every record plans
clean, and a study that breaks a rule is refused by name with the rule's own
message."""
from __future__ import annotations

import pytest

from cardiacfoam_native import native_tutorials_root
from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError

pytestmark = pytest.mark.native

_COEFFS = "constant/electroProperties:"


def _plan(record: str, tmp_path, study: dict | None = None):
    return strict_plan(
        record, overrides={"cases_root": str(native_tutorials_root()), **(study or {})},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


@pytest.mark.parametrize("record", sorted(TUTORIAL_RECORDS))
def test_every_record_plans_clean(record, tmp_path):
    report = _plan(record, tmp_path)
    assert report.status == "ok", [d.message for d in report.validation_diagnostics + report.artifact_diagnostics]


@pytest.mark.parametrize(("record", "study", "fragments"), [
    # A cross-field rule: a tissue label the ionic model does not accept.
    (
        "singleCell",
        {"ionicModel": "AlievPanfilovcompactBatched", _COEFFS + "singleCellSolverCoeffs.tissue": "epicardialCells"},
        ("tissue 'epicardialCells' is not in the compatible tissues for ionicModel 'AlievPanfilovcompactBatched'",),
    ),
    # A cross-field rule: a coupler the solver pair does not admit.
    (
        "manufacturedMonodomain1D3D",
        {_COEFFS + "monodomainSolverCoeffs.domainCouplings.couplingA.electroDomainCoupler": "eikonalPvjCoupler"},
        ("domainCouplings.couplingA.electroDomainCoupler", "expected reactionDiffusionPvjCoupler"),
    ),
    # A relation the catalogue states: a scalar ionic model builds OpenFOAM's
    # ODESolver, which this case's batched model never needed.
    (
        "niederer2011",
        {_COEFFS + "monodomainSolverCoeffs.ionicModel": "TNNP"},
        ("solver is required when ionicModel in (", "maxSteps is required when ionicModel in ("),
    ),
])
def test_a_study_that_breaks_a_rule_is_refused_before_it_runs(record, study, fragments, tmp_path):
    with pytest.raises(TutorialRecordError) as exc:
        _plan(record, tmp_path, study)
    message = str(exc.value)
    assert f"tutorial record {record!r}: the resolved case breaks" in message
    for fragment in fragments:
        assert fragment in message, (fragment, message)
