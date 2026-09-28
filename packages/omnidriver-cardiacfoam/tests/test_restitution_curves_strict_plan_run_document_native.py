"""`plan --strict --entry restitutionCurves` and its advertised `run --run-document` reach a completed real cardiacFoam solve.
The coarse mesh is a study value (the `blockMeshResolution` axis), never a case-file edit.
``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered: this test fails, not skips, without it.
"""

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
    """Copy the native case into scratch; the native tree is never written."""
    native_case = native_root / _RESTITUTION_CURVES_RELPATH
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")

    scratch_case = scratch_root / "tutorials" / _RESTITUTION_CURVES_RELPATH
    shutil.copytree(native_case, scratch_case)

    return scratch_root / "tutorials"


def test_restitution_curves_plan_strict_and_its_advertised_run_document_reach_completed(
    tmp_path: Path,
) -> None:
    native_root = native_tutorials_root()
    cases_root = _stage_scratch_copy(native_root, tmp_path / "native-scratch")

    # The first point of the native tworldS1S2Restitution/sweep.json, as this case's study `base`.
    config = {
        "restitutionCurves": {
            "ionicModel": "TWorld",
            "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            "blockMeshResolution": [40, 6, 14],
            "s1s2Protocol": {
                "s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 1500,
            },
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    from omnidriver.cli import main

    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "plan", "--strict", "--entry", "restitutionCurves",
            "--config", str(config_path),
            "--cases-root", str(cases_root),
            "--scratch-dir", str(tmp_path / "scratch"),
        ])
    plan_payload = json.loads(out.getvalue())
    assert code == 0, plan_payload
    assert plan_payload["status"] == "ok", plan_payload

    command = plan_payload["launch"]["command"]
    assert "--run-document" in command, command
    assert "--strict" not in command
    assert "--entry" not in command
    run_document_path = Path(command[command.index("--run-document") + 1])
    assert run_document_path.is_file(), (
        "plan --strict must persist the run document it advertises, so the "
        "command it prints is immediately runnable"
    )
    committed_document = json.loads(run_document_path.read_text())
    assert committed_document["configurationSource"] == "case"
    case_root = Path(committed_document["launch"]["caseRoot"])

    # Run the advertised command in-process, dropping its `python -m omnidriver` prefix.
    assert command[:3] == [command[0], "-m", "omnidriver"]
    out = StringIO()
    with redirect_stdout(out):
        code = main(command[3:])
    run_payload = json.loads(out.getvalue())
    assert code == 0, run_payload
    assert run_payload["status"] == "ok", run_payload
    workflow_state = run_payload["workflow_state"]
    assert workflow_state["status"] == "completed", workflow_state
    assert workflow_state["completed_steps"] == ["mesh", "solve"]
    assert workflow_state["failed_step_id"] is None
    for step in run_payload["steps"]:
        assert step["exit_code"] == 0, step

    trace_files = list((case_root / "postProcessing").glob("*.txt"))
    assert trace_files, "cardiacFoam wrote no postProcessing trace file"
    trace_lines = trace_files[0].read_text().splitlines()
    assert len(trace_lines) > 1000, (
        f"expected a real multi-timestep trace, got {len(trace_lines)} lines"
    )

    # The `blockMeshResolution` patch reached the case through `plan --strict`'s own commit channel.
    block_mesh_dict = (case_root / "system" / "blockMeshDict").read_text()
    active_hex_lines = [
        line.strip() for line in block_mesh_dict.splitlines()
        if line.strip().startswith("hex (")
    ]
    assert len(active_hex_lines) == 1, (
        f"expected exactly one active hex block, got {active_hex_lines}"
    )
    assert "(40 6 14)" in active_hex_lines[0], active_hex_lines[0]
