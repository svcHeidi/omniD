"""The catalogue's rules and cardiacFOAM's cross-field rules on the resolved case of a native record,
committed verbatim as a fixture: it plans clean, and a study that breaks a rule is refused by name
with the rule's own message, before anything executes."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError

TUTORIALS = Path(__file__).resolve().parent / "fixtures" / "tutorials"
COEFFS = "constant/electroProperties:"


def _plan(record: str, tmp_path, study: dict | None = None):
    return strict_plan(
        record, overrides={"cases_root": str(TUTORIALS), **(study or {})},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


@pytest.mark.parametrize("record", ["singleCell", "restitutionCurves"])
def test_a_native_record_plans_clean(record, tmp_path):
    report = _plan(record, tmp_path)
    assert report.status == "ok", [d.message for d in report.plugin_diagnostics if d.level == "error"]


@pytest.mark.parametrize(("study", "fragments"), [
    # A cross-field rule: a tissue label the ionic model does not accept.
    (
        {"ionicModel": "AlievPanfilovcompactBatched", COEFFS + "singleCellSolverCoeffs.tissue": "epicardialCells"},
        ("tissue 'epicardialCells' is not in the compatible tissues for ionicModel 'AlievPanfilovcompactBatched'",),
    ),
    # A value outside the menu the catalogue lists.
    (
        {COEFFS + "singleCellSolverCoeffs.tissue": "nowhere"},
        ("tissue is 'nowhere', not one of the values",),
    ),
])
def test_a_study_that_breaks_a_rule_is_refused_before_it_runs(study, fragments, tmp_path):
    with pytest.raises(TutorialRecordError) as exc:
        _plan("singleCell", tmp_path, study)
    message = str(exc.value)
    assert "tutorial record 'singleCell': the resolved case breaks" in message
    for fragment in fragments:
        assert fragment in message, (fragment, message)


def test_a_misspelled_key_is_a_warning_and_never_fails_the_plan(tmp_path):
    cases_root = tmp_path / "tutorials"
    shutil.copytree(TUTORIALS, cases_root)
    ep = cases_root / "electrophysiologyProtocols" / "singleCell" / "constant" / "electroProperties"
    ep.write_text(ep.read_text().replace("writeFrequency  0.001;", "writeFrequenc  0.001;"))
    report = strict_plan(
        "singleCell", overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )
    assert report.status == "ok"
    warnings = [d for d in report.plugin_diagnostics if d.code == "uncatalogued_case_dict_key"]
    assert [(d.field, d.level) for d in warnings] == [("writeFrequenc", "warning")]
