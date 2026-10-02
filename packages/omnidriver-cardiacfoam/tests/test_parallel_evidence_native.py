"""A parallel ``niederer2011`` ran decomposed on the requested ranks: C13 compares values, and this
is the evidence those values did not come from N serial copies."""
from __future__ import annotations

import pytest

from omnidriver.conformance import record_run, require_commands
from cardiacfoam_native import native_tutorials_root

pytestmark = pytest.mark.native

RANKS = 2


def test_the_parallel_run_ran_on_the_decomposed_ranks(tmp_path):
    require_commands("blockMesh", "cardiacFoam", "decomposePar", "reconstructPar", "mpirun")
    run = record_run(
        tmp_path, plugin="cardiacfoam", record="niederer2011", cases_root=native_tutorials_root(),
        sweep={"dx": [0.0005]},
        study={"system/controlDict:endTime": 0.015, "parallel": RANKS,
               "system/decomposeParDict:numberOfSubdomains": RANKS},
    )
    log = (run.case_root / "workflow_logs" / "solve.attempt1.stdout.log").read_text()
    assert f"nProcs : {RANKS}" in log
    assert sorted(p.name for p in run.case_root.glob("processor*")) == [f"processor{k}" for k in range(RANKS)]
