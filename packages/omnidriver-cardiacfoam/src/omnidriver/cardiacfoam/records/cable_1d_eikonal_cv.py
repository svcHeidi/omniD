"""``cable1DEikonalCV``, the eikonal conduction-velocity record on the 1D cable.
Native case: ``electrophysiologyProtocols/cableProtocol/eikonal1DCableCV``; ``blockMesh``, ``cardiacFoam``, then the
case's own ``setup/extract_cv.py``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .cable_axes import cable_dx_axis
from .case_outputs import WITH_DEFAULT_VALUES
from .routes import block_mesh_step, cable_cv_summary_step, redistribute_restart_state_step, solve_step

DX_AXIS_NAME = "dx"

AXES = (
    cable_dx_axis(DX_AXIS_NAME),
)

RECORD = TutorialRecord(
    name="cable1DEikonalCV",
    native_case_relpath="electrophysiologyProtocols/cableProtocol/eikonal1DCableCV",
    axes=AXES,
    workflow_steps=(
        block_mesh_step(("system/blockMeshDict", "system/controlDict")),
        solve_step(
            (
                WITH_DEFAULT_VALUES,
                "postProcessing/cableProbes/*/Vm",
                "postProcessing/cableProbes/*/activationTime",
            ),
            consumes=("0/activationTime", "system/cableProbes"),
        ),
        redistribute_restart_state_step(),
        cable_cv_summary_step(),
    ),
)
