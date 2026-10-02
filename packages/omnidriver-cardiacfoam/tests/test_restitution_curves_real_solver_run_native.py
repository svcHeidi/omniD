"""The ``restitutionCurves`` record, run end to end through the real ``omnidriver`` CLI, cardiacFoam binary and OpenFOAM runtime.

The coarse mesh comes from the study's ``blockMeshResolution`` axis through the record's commit channel, never an edit here."""

from __future__ import annotations

import json
import shutil
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from cardiacfoam_native import native_tutorials_root

pytestmark = [pytest.mark.native, pytest.mark.slow]

_RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"


def _stage_scratch_copy(native_root: Path, scratch_root: Path) -> Path:
    """Copy the native case into scratch; neither the native tree nor the copy is edited here."""
    native_case = native_root / _RESTITUTION_CURVES_RELPATH
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")

    scratch_case = scratch_root / "tutorials" / _RESTITUTION_CURVES_RELPATH
    shutil.copytree(native_case, scratch_case)

    return scratch_root / "tutorials"


def test_restitution_curves_single_case_reaches_completed_via_the_real_cli(
    tmp_path: Path,
) -> None:
    native_root = native_tutorials_root()
    cases_root = _stage_scratch_copy(native_root, tmp_path / "native-scratch")

    # One case: the first S2 value tworldS1S2Restitution/sweep.json sweeps, a
    # real protocol point. `blockMeshResolution` picks the tutorial's smallest
    # documented mesh (40x6x14, one of blockMeshDict's commented alternatives)
    # instead of 200x30x70 only so the solve takes seconds; physics are unchanged.
    spec = {
        "base": {
            "entry": "restitutionCurves",
            "cases_root": str(cases_root),
            "ionicModel": "TWorld",
            "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            "blockMeshResolution": [40, 6, 14],
        },
        "sweep": {
            "mode": "zip",
            "independent": {
                "s1s2Protocol": [
                    {"s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 1500},
                ],
            },
        },
    }
    spec_path = tmp_path / "scratch_sweep.json"
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"

    from omnidriver.cli import main

    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "sweep-run", "--spec", str(spec_path), "--output-dir", str(output_dir),
        ])

    result = json.loads(out.getvalue())
    assert code == 0, result
    assert result["completed_count"] == 1, result
    assert result["failed_count"] == 0, result
    [case] = result["cases"]
    assert case["status"] == "completed", case

    workflow_state = json.loads(
        (output_dir / "cases" / "case_0001" / "workflow_state.json").read_text()
    )
    assert workflow_state["status"] == "completed"
    assert workflow_state["completed_steps"] == ["mesh", "solve"]
    assert workflow_state["failed_step_id"] is None
    for step in workflow_state["steps"]:
        assert step["status"] == "completed", step
        assert step["exit_code"] == 0, step

    # A real solve writes a multi-sample postProcessing trace, not an empty stub.
    solved_case = output_dir / "cases" / "case_0001"
    trace_files = list((solved_case / "postProcessing").glob("*.txt"))
    assert trace_files, "cardiacFoam wrote no postProcessing trace file"
    trace_lines = trace_files[0].read_text().splitlines()
    assert len(trace_lines) > 1000, (
        f"expected a real multi-timestep trace, got {len(trace_lines)} lines"
    )

    # The `blockMeshResolution` patch reached the case through the commit channel.
    block_mesh_dict = (solved_case / "system" / "blockMeshDict").read_text()
    active_hex_lines = [
        line.strip() for line in block_mesh_dict.splitlines()
        if line.strip().startswith("hex (")
    ]
    assert len(active_hex_lines) == 1, (
        f"expected exactly one active hex block, got {active_hex_lines}"
    )
    assert "(40 6 14)" in active_hex_lines[0], active_hex_lines[0]
