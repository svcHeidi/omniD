"""``rotorInstability``, the self-sustained rotor tutorial record.
Native case: ``electrophysiologyProtocols/rotorInstability``; the native ``Allrun``'s ``blockMesh``, ``cardiacFoam``, ``postProcess``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import WITH_DEFAULT_VALUES
from .routes import block_mesh_step, redistribute_restart_state_step, solve_step

#: `controlDict` runs the `rotorpoints` function during the solve too; the
#: probe file is declared on the step that rewrites it last.
_ROTOR_POINTS_FUNCTION = "rotorpoints"

RECORD = TutorialRecord(
    name="rotorInstability",
    native_case_relpath="electrophysiologyProtocols/rotorInstability",
    workflow_steps=(
        block_mesh_step(("system/blockMeshDict", "system/controlDict")),
        solve_step((WITH_DEFAULT_VALUES,), consumes=("system/rotorpoints",)),
        redistribute_restart_state_step(),
        WorkflowStep(
            step_id="samplePoints",
            command=("postProcess", "-func", _ROTOR_POINTS_FUNCTION, "-latestTime"),
            produces=("postProcessing/rotorpoints/*/activationTime",),
        ),
    ),
)
