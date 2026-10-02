"""``step --apply`` on a real cardiacFOAM case: the patches land in the staged case's own dictionaries, and the step reruns against them."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.conformance import record_step, require_commands
from omnidriver.openfoam.mutators import read_foam_entry
from cardiacfoam_native import native_tutorials_root

pytestmark = pytest.mark.native


def test_apply_edits_the_staged_case_then_the_solver_runs_against_it(tmp_path):
    require_commands("blockMesh", "cardiacFoam")
    case_root, payload = record_step(
        tmp_path, plugin="cardiacfoam", record="singleCell", cases_root=native_tutorials_root(),
        before=("mesh",), step="solve",
        apply={
            "system/controlDict:endTime": 0.05,
            "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
        },
    )

    assert payload["status"] == "ok", payload
    assert {patch["status"] for patch in payload["applied_patches"]} == {"changed"}
    assert read_foam_entry(case_root / "system" / "controlDict", "endTime") == "0.05"
    assert read_foam_entry(
        case_root / "constant" / "electroProperties", "tissue", scope=["singleCellSolverCoeffs"],
    ) == "epicardialCells"
    # The solver ran against the edit: it stopped at the new endTime and named its result after the new tissue.
    assert "\nTime = 0.05\n" in Path(payload["stdout_log"]).read_text()
    assert (case_root / "postProcessing" / "TWorld_epicardialCells_S1_1000.txt").is_file()
