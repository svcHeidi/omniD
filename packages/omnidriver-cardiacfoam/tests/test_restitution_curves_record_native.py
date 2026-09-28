"""``restitutionCurves`` against the real native tree: an empty study proposes
zero patches (the native case is the default), and the ionic-model catalog's
stimulus amplitudes (TWorld 60, BuenoOrovio 0.4) match the real case files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cardiacfoam_native import native_tutorials_root

from omnidriver.cardiacfoam.records.restitution_curves import RECORD
from omnidriver.core.tutorial_records import sort_study_name
from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime import record_execution
from omnidriver.openfoam.case_planning import read_hex_cell_counts

pytestmark = pytest.mark.native

_RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
_SINGLE_CELL_RELPATH = "electrophysiologyProtocols/singleCell"


def _cardiac_stack():
    return load_discovered_plugin("cardiacfoam")


def _read_stim_amplitude(case_root: Path) -> float:
    text = (case_root / "constant" / "electroProperties").read_text()
    match = re.search(r"stim_amplitude\s+([^\s;]+);", text)
    assert match is not None, f"fixture {case_root} has no stim_amplitude entry"
    return float(match.group(1))


def _read_ionic_model(case_root: Path) -> str:
    text = (case_root / "constant" / "electroProperties").read_text()
    match = re.search(r"ionicModel\s+([^\s;]+);", text)
    assert match is not None, f"fixture {case_root} has no ionicModel entry"
    return match.group(1)


def test_restitution_curves_preview_with_no_study_values_shows_zero_changes():
    tutorials_root = native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    context = _cardiac_stack()

    preview = record_execution.preview_record_case(
        RECORD, cases_root=tutorials_root, study_by_source={},
        driver_context=context,
    )

    assert preview["patches"] == [], (
        "the native case is the default: an empty study must propose "
        f"nothing, got {preview['patches']!r}"
    )
    assert preview["workflow_step_ids"] == ["mesh", "solve"]


def test_restitution_curves_block_mesh_resolution_axis_reports_the_active_resolution_unchanged():
    tutorials_root = native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    context = _cardiac_stack()

    active_text = read_hex_cell_counts(case_root / "system" / "blockMeshDict")
    assert active_text is not None, "blockMeshDict has no readable active hex block"
    active_resolution = [int(part) for part in active_text.split()]
    assert len(active_resolution) == 3

    preview = record_execution.preview_record_case(
        RECORD, cases_root=tutorials_root,
        study_by_source={"base": {"blockMeshResolution": active_resolution}},
        driver_context=context,
    )

    [patch] = preview["patches"]
    assert patch["document"] == "system/blockMeshDict"
    # The axis patches a typed tuple, not the file's pre-joined text.
    assert patch["value"] == tuple(active_resolution)
    assert patch["status"] == "unchanged", preview


def test_the_single_cell_native_case_confirms_tworld_sixty():
    tutorials_root = native_tutorials_root()
    case_root = tutorials_root / _SINGLE_CELL_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    assert _read_ionic_model(case_root) == "TWorld"
    native_amplitude = _read_stim_amplitude(case_root)
    assert native_amplitude == 60.0

    axis = sort_study_name("ionicModel", axes=RECORD.axes).axis
    result = axis.resolve("TWorld", case_root)
    by_key_path = {patch.key_path: patch for patch in result.patches}
    axis_amplitude = by_key_path[
        ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")
    ].value
    assert axis_amplitude == native_amplitude


def test_the_restitution_curves_native_case_confirms_buenoorovio_zero_point_four():
    tutorials_root = native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    assert _read_ionic_model(case_root) == "BuenoOrovio"
    native_amplitude = _read_stim_amplitude(case_root)
    assert native_amplitude == 0.4

    axis = sort_study_name("ionicModel", axes=RECORD.axes).axis
    result = axis.resolve("BuenoOrovio", case_root)
    by_key_path = {patch.key_path: patch for patch in result.patches}
    axis_amplitude = by_key_path[
        ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")
    ].value
    assert axis_amplitude == native_amplitude


def test_commit_record_case_writes_a_real_case_via_the_real_renderer(tmp_path):
    """Guards against commit_record_case conflating snapshot_root and case_root."""
    tutorials_root = native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    context = _cardiac_stack()
    staged_case_root = tmp_path / "staged"

    result = record_execution.commit_record_case(
        RECORD, cases_root=tutorials_root, staged_case_root=staged_case_root,
        study_by_source={
            "base": {
                "ionicModel": "TWorld",
                "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            },
            "sweep": {
                "s1s2Protocol": {
                    "s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2,
                    "s2_interval_ms": 250,
                },
            },
        },
        driver_context=context,
    )

    assert result.status == "committed"
    written = (staged_case_root / "constant" / "electroProperties").read_text()
    assert "ionicModel    TWorld;" in written
    assert "stim_amplitude    60.0;" in written
    control_dict = (staged_case_root / "system" / "controlDict").read_text()
    # end_time = (1000 * 9 + 250 * 2) / 1000.0 + 2.0 == 11.5
    assert re.search(r"endTime\s+11\.5;", control_dict)
