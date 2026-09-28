"""Record key validation, comparison and reading on the real cardiac stack against
the native ``restitutionCurves_s1s2Protocol`` case. Every asserted value is read
from the case's own files at test time; no test doubles.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime import record_execution
from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError, WorkflowStep

pytestmark = pytest.mark.native

_RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
_STIM_AMPLITUDE_KEY_PATH = (
    "singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude",
)
_STIM_AMPLITUDE_STUDY_NAME = (
    "constant/electroProperties:" + ".".join(_STIM_AMPLITUDE_KEY_PATH)
)
_DELTA_T_STUDY_NAME = "system/controlDict:deltaT"
_HEX_CELL_COUNTS_STUDY_NAME = "system/blockMeshDict:hex_cell_counts"


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _real_case_root() -> Path:
    root = _native_tutorials_root()
    case_root = root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    return case_root


def _read_stim_amplitude(case_root: Path) -> float:
    text = (case_root / "constant" / "electroProperties").read_text()
    match = re.search(r"stim_amplitude\s+([^\s;]+);", text)
    assert match is not None, "fixture has no stim_amplitude entry"
    return float(match.group(1))


def _read_delta_t(case_root: Path) -> float:
    text = (case_root / "system" / "controlDict").read_text()
    match = re.search(r"deltaT\s+([^\s;]+);", text)
    assert match is not None, "fixture has no deltaT entry"
    return float(match.group(1))


def _read_hex_cell_counts(case_root: Path) -> str:
    text = (case_root / "system" / "blockMeshDict").read_text()
    real_hex_lines = [
        line for line in text.splitlines() if line.strip().startswith("hex (")
    ]
    assert len(real_hex_lines) == 1, (
        f"fixture expected exactly one real hex ( block, found "
        f"{len(real_hex_lines)}"
    )
    match = re.search(r"\)\s*\(([^)]*)\)\s*simpleGrading", real_hex_lines[0])
    assert match is not None, "fixture's hex ( line has no cell-count group"
    return match.group(1)


def _test_record() -> TutorialRecord:
    """No axes: every restated value is a plain ``document:dotted.path`` study key."""
    return TutorialRecord(
        name="restitutionCurvesRecordTest",
        native_case_relpath=_RESTITUTION_CURVES_RELPATH,
        workflow_steps=(WorkflowStep(step_id="solve", command=("cardiacFoam",)),),
    )


def _cardiac_stack():
    return load_discovered_plugin("cardiacfoam")


def test_the_real_cardiac_stack_answers_all_three_capabilities():
    case_root = _real_case_root()  # every test in this module needs the native root
    del case_root
    context = _cardiac_stack()
    assert context.capabilities.record_key_validation.validator() is not None
    assert context.capabilities.case_value_comparison.comparator() is not None
    assert context.capabilities.config_value.reader() is not None


def test_a_catalogued_electro_properties_key_validates_true():
    case_root = _real_case_root()
    stim_amplitude = _read_stim_amplitude(case_root)
    validator = _cardiac_stack().capabilities.record_key_validation.validator()

    value_kind, validated = validator(
        "constant/electroProperties", _STIM_AMPLITUDE_KEY_PATH, stim_amplitude,
    )

    assert value_kind == "scalar"
    assert validated is True


def test_a_misspelled_key_is_refused():
    case_root = _real_case_root()
    stim_amplitude = _read_stim_amplitude(case_root)
    validator = _cardiac_stack().capabilities.record_key_validation.validator()

    with pytest.raises(KeyError):
        validator(
            "constant/electroProperties",
            ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitud"),
            stim_amplitude,
        )


def test_a_misspelled_key_is_refused_through_preview_record_case():
    case_root = _real_case_root()
    stim_amplitude = _read_stim_amplitude(case_root)
    context = _cardiac_stack()
    record = _test_record()
    bad_study = {
        "base": {
            "constant/electroProperties:singleCellSolverCoeffs.singleCellStimulus."
            "stim_amplitud": stim_amplitude,
        },
    }

    with pytest.raises(TutorialRecordError):
        record_execution.preview_record_case(
            record, cases_root=case_root.parent.parent,
            study_by_source=bad_study, driver_context=context,
        )


def test_system_control_dict_delta_t_validates_false():
    case_root = _real_case_root()
    delta_t = _read_delta_t(case_root)
    validator = _cardiac_stack().capabilities.record_key_validation.validator()

    value_kind, validated = validator("system/controlDict", ("deltaT",), delta_t)

    assert value_kind == "scalar"
    assert validated is False


def test_restating_the_cases_own_current_values_is_reported_unchanged():
    case_root = _real_case_root()
    stim_amplitude = _read_stim_amplitude(case_root)
    delta_t = _read_delta_t(case_root)
    hex_cell_counts = _read_hex_cell_counts(case_root)
    context = _cardiac_stack()
    record = _test_record()
    study = {
        "base": {
            _STIM_AMPLITUDE_STUDY_NAME: stim_amplitude,
            _DELTA_T_STUDY_NAME: delta_t,
            _HEX_CELL_COUNTS_STUDY_NAME: hex_cell_counts,
        },
    }

    preview = record_execution.preview_record_case(
        record, cases_root=case_root.parent.parent,
        study_by_source=study, driver_context=context,
    )

    patches_by_key_path = {
        tuple(patch["key_path"]): patch for patch in preview["patches"]
    }
    assert len(patches_by_key_path) == 3

    stim_amplitude_patch = patches_by_key_path[_STIM_AMPLITUDE_KEY_PATH]
    assert stim_amplitude_patch["status"] == "unchanged"
    assert stim_amplitude_patch["validated"] is True

    delta_t_patch = patches_by_key_path[("deltaT",)]
    assert delta_t_patch["status"] == "unchanged"
    assert delta_t_patch["validated"] is False

    hex_cell_counts_patch = patches_by_key_path[("hex_cell_counts",)]
    assert hex_cell_counts_patch["status"] == "unchanged"
    assert hex_cell_counts_patch["validated"] is False


def test_a_different_value_is_reported_changed_not_unconditionally_unchanged():
    case_root = _real_case_root()
    delta_t = _read_delta_t(case_root)
    context = _cardiac_stack()
    record = _test_record()
    study = {
        "base": {
            _DELTA_T_STUDY_NAME: delta_t * 2,
            _HEX_CELL_COUNTS_STUDY_NAME: "999 999 999",
        },
    }

    preview = record_execution.preview_record_case(
        record, cases_root=case_root.parent.parent,
        study_by_source=study, driver_context=context,
    )

    assert all(patch["status"] == "changed" for patch in preview["patches"])
