"""The Niederer 2011 N-version benchmark, as the solver repository's cases/nversion states it.

One step: the repository's runner turns case.json into TorchCor calls. dx, dt
and every other value are case.json keys, so a study names them directly
(``case.json:dx_mm``) and the record declares no axis."""
from __future__ import annotations

from omnidriver.core.tutorial_records import ProducedPath, TutorialRecord, WorkflowStep

from ..activation_reader import ACTIVATION_FORMAT

RECORD = TutorialRecord(
    name="nversion",
    native_case_relpath="nversion",
    # One process on one device; TorchCor has no MPI (docs/solver-learning/torchcor.md E).
    serial_only=True,
    workflow_steps=(
        WorkflowStep(
            step_id="solve",
            command=("run_case.py", "case.json"),
            consumes=("case.json",),
            produces=(
                "mesh", "stim.vtx", "out",
                ProducedPath("out/activation_times.dat", format=ACTIVATION_FORMAT), "out/run_info.json",
            ),
        ),
    ),
)
