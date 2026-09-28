"""``cable1DCVConvergence``: a tutorial record for the same case
``cable1DRestitution`` points at,
``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV``. Runs
``blockMesh`` then ``cardiacFoam``, with no postprocess step: CV extraction is
a manual script, never wired through ``Allrun``/``Allrun.post``. See
``docs/solver-learning/cardiacfoam.md`` section CABLE.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .cable_axes import cable_dx_axis
from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES

DX_AXIS_NAME = "dx"

AXES = (
    cable_dx_axis(DX_AXIS_NAME),
)

RECORD = TutorialRecord(
    name="cable1DCVConvergence",
    native_case_relpath="electrophysiologyProtocols/cableProtocol/monodomain1DCableCV",
    axes=AXES,
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            consumes=("system/blockMeshDict", "system/controlDict"),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES, "system/cableProbes",
            ),
            produces=(WITH_DEFAULT_VALUES, "postProcessing/cableProbes/*/Vm"),
        ),
    ),
)
