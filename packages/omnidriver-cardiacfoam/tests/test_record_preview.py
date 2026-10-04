"""Records over native cases committed verbatim as fixtures (``constant/`` and ``system/`` of
``restitutionCurves_s1s2Protocol`` and ``singleCell``): preview, validation flags, axes and the real
renderer, on the real cardiac stack. Nothing runs a solver."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records.restitution_curves import RECORD
from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime import record_execution
from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError, WorkflowStep, sort_study_name
from omnidriver.openfoam.case_planning import read_hex_cell_counts

TUTORIALS = Path(__file__).resolve().parent / "fixtures" / "tutorials"
RESTITUTION = TUTORIALS / "electrophysiologyProtocols" / "restitutionCurves_s1s2Protocol"
SINGLE_CELL = TUTORIALS / "electrophysiologyProtocols" / "singleCell"
STIM_AMPLITUDE = ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")
STIM_AMPLITUDE_STUDY_NAME = "constant/electroProperties:" + ".".join(STIM_AMPLITUDE)


def _stack():
    return load_discovered_plugin("cardiacfoam")


def _read(case: Path, document: str, key: str) -> str:
    match = re.search(rf"{key}\s+([^\s;]+);", (case / document).read_text())
    assert match is not None, f"{case / document} has no {key}"
    return match.group(1)


def _plain_record() -> TutorialRecord:
    """No axes: every restated value is a plain ``document:dotted.path`` study key."""
    return TutorialRecord(
        name="restitutionCurvesRecordTest",
        native_case_relpath="electrophysiologyProtocols/restitutionCurves_s1s2Protocol",
        workflow_steps=(WorkflowStep(step_id="solve", command=("cardiacFoam",)),),
    )


def _preview(record, study):
    return record_execution.preview_record_case(
        record, cases_root=TUTORIALS, study_by_source=study, driver_context=_stack(),
    )


def test_an_empty_study_proposes_nothing_because_the_native_case_is_the_default():
    preview = _preview(RECORD, {})
    assert preview["patches"] == []
    assert preview["workflow_step_ids"] == ["mesh", "solve"]


def test_the_block_mesh_resolution_axis_reports_the_active_resolution_unchanged():
    active = [int(part) for part in read_hex_cell_counts(RESTITUTION / "system" / "blockMeshDict").split()]
    [patch] = _preview(RECORD, {"base": {"blockMeshResolution": active}})["patches"]
    assert (patch["document"], patch["value"], patch["status"]) == ("system/blockMeshDict", tuple(active), "unchanged")


def test_restating_the_cases_own_values_is_unchanged_and_flags_what_the_catalogue_validates():
    amplitude = float(_read(RESTITUTION, "constant/electroProperties", "stim_amplitude"))
    delta_t = float(_read(RESTITUTION, "system/controlDict", "deltaT"))
    cells = read_hex_cell_counts(RESTITUTION / "system" / "blockMeshDict")
    preview = _preview(_plain_record(), {"base": {
        STIM_AMPLITUDE_STUDY_NAME: amplitude, "system/controlDict:deltaT": delta_t,
        "system/blockMeshDict:hex_cell_counts": cells,
    }})
    patches = {tuple(patch["key_path"]): patch for patch in preview["patches"]}
    assert len(patches) == 3
    assert (patches[STIM_AMPLITUDE]["status"], patches[STIM_AMPLITUDE]["validated"]) == ("unchanged", True)
    assert (patches[("deltaT",)]["status"], patches[("deltaT",)]["validated"]) == ("unchanged", True)
    assert (patches[("hex_cell_counts",)]["status"], patches[("hex_cell_counts",)]["validated"]) == ("unchanged", False)


def test_a_different_value_is_changed_not_unconditionally_unchanged():
    delta_t = float(_read(RESTITUTION, "system/controlDict", "deltaT"))
    preview = _preview(_plain_record(), {"base": {
        "system/controlDict:deltaT": delta_t * 2, "system/blockMeshDict:hex_cell_counts": "999 999 999",
    }})
    assert all(patch["status"] == "changed" for patch in preview["patches"])


def test_a_misspelled_key_is_refused_through_the_preview():
    study = {"base": {"constant/electroProperties:singleCellSolverCoeffs.singleCellStimulus.stim_amplitud": 0.4}}
    with pytest.raises(TutorialRecordError):
        _preview(_plain_record(), study)


@pytest.mark.parametrize("model, case, amplitude", [("TWorld", SINGLE_CELL, 60.0), ("BuenoOrovio", RESTITUTION, 0.4)])
def test_the_ionic_model_axis_proposes_the_stimulus_amplitude_the_native_case_holds(model, case, amplitude):
    assert _read(case, "constant/electroProperties", "ionicModel") == model
    assert float(_read(case, "constant/electroProperties", "stim_amplitude")) == amplitude
    result = sort_study_name("ionicModel", axes=RECORD.axes).axis.resolve(model, case)
    assert {patch.key_path: patch for patch in result.patches}[STIM_AMPLITUDE].value == amplitude


def test_commit_record_case_writes_a_real_case_via_the_real_renderer(tmp_path):
    """Guards against commit_record_case conflating snapshot_root and case_root."""
    result = record_execution.commit_record_case(
        RECORD, cases_root=TUTORIALS, staged_case_root=tmp_path / "staged", driver_context=_stack(),
        study_by_source={
            "base": {
                "ionicModel": "TWorld",
                "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            },
            "sweep": {"s1s2Protocol": {"s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 250}},
        },
    )
    assert result.status == "committed"
    written = (tmp_path / "staged" / "constant" / "electroProperties").read_text()
    assert "ionicModel    TWorld;" in written and "stim_amplitude    60.0;" in written
    # end_time = (1000 * 9 + 250 * 2) / 1000.0 + 2.0 == 11.5
    assert re.search(r"endTime\s+11\.5;", (tmp_path / "staged" / "system" / "controlDict").read_text())


def test_describe_and_a_strict_plan_carry_the_capability_manifest(tmp_path):
    from omnidriver.core.introspection import describe_entry
    from omnidriver.core.strict_planning import strict_plan

    context = _stack()
    overrides = {"cases_root": str(TUTORIALS)}
    manifest = describe_entry("singleCell", overrides=overrides, driver_context=context)["capability_manifest"]
    assert "cardiacFoam" in manifest["allowed_commands"]["plugin"]
    assert "electro" in manifest["samplable_fields"]
    report = strict_plan("singleCell", overrides=overrides, driver_context=context, scratch_root=str(tmp_path / "scratch")).to_json()
    assert "cardiacFoam" in report["capability_manifest"]["allowed_commands"]["plugin"]


def test_apply_edits_the_staged_cases_own_dictionaries_through_the_real_renderer(tmp_path):
    from omnidriver.core.plugin_discovery import load_discovered_plugin as _load
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease
    from omnidriver.core.strict_planning import strict_plan
    from omnidriver.openfoam.mutators import read_foam_entry

    context = _load("cardiacfoam")
    report = strict_plan(
        "singleCell", overrides={"cases_root": str(TUTORIALS)}, driver_context=context, scratch_root=str(tmp_path / "scratch"),
    )
    case_root = Path(report.launch["case_root"])
    record = context.stack.call("get_tutorial_records")["singleCell"]
    with acquire_case_lease(case_root):
        applied = record_execution.apply_record_study(
            record, case_root=case_root, driver_context=context,
            study={"system/controlDict:endTime": 0.05, "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells"},
        )
    assert {patch["status"] for patch in applied} == {"changed"}
    assert read_foam_entry(case_root / "system" / "controlDict", "endTime") == "0.05"
    assert read_foam_entry(case_root / "constant" / "electroProperties", "tissue", scope=["singleCellSolverCoeffs"]) == "epicardialCells"


def test_single_cell_refuses_a_parallel_run_by_name():
    from omnidriver.cardiacfoam.records.single_cell import RECORD as SINGLE_CELL_RECORD

    with pytest.raises(TutorialRecordError, match="'singleCell' is serial only"):
        record_execution.preview_record_case(
            SINGLE_CELL_RECORD, cases_root=TUTORIALS, study_by_source={"base": {"parallel": True}},
            driver_context=_stack(),
        )
