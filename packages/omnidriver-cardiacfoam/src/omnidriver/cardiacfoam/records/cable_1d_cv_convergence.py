"""``cable1DCVConvergence``, the ``dx`` convergence record on the same case as ``cable1DRestitution``.
Runs ``blockMesh``, ``cardiacFoam``, then the case's own ``setup/extract_cv.py``, which ``Allrun`` leaves to a manual
call.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .cable_axes import cable_dx_axis
from .case_outputs import WITH_DEFAULT_VALUES
from .routes import block_mesh_step, cable_cv_summary_step, solve_step

DX_AXIS_NAME = "dx"

AXES = (
    cable_dx_axis(DX_AXIS_NAME),
)

RECORD = TutorialRecord(
    name="cable1DCVConvergence",
    native_case_relpath="electrophysiologyProtocols/cableProtocol/monodomain1DCableCV",
    axes=AXES,
    workflow_steps=(
        block_mesh_step(("system/blockMeshDict", "system/controlDict")),
        solve_step(
            (WITH_DEFAULT_VALUES, "postProcessing/cableProbes/*/Vm", "postProcessing/cableProbes/*/activationTime"),
            consumes=("system/cableProbes",),
        ),
        cable_cv_summary_step(),
    ),
)
