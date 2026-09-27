"""``singleCell``: a tutorial record for ``electrophysiologyProtocols/singleCell``.

The native ``Allrun``'s commands, ``blockMesh`` then ``cardiacFoam``, on one
cell running ``singleCellSolver``. The case has no mesh study, so there is no
mesh axis and no tet route. ``ionicModel`` reuses ``restitutionCurves``' axis,
because the catalog pairs each model with its stimulus amplitude. Everything
else the two native studies vary (``tissue``, ``stim_period_S1``,
``outputVariables.ionic.export``) is a direct key. What each step reads and
writes was observed in a real run: ``docs/solver-learning/cardiacfoam.md`` SC.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS
from .ionic_model_axis import ionic_model_axis

_SINGLE_CELL_SOLVER_COEFFS = ("singleCellSolverCoeffs",)

IONIC_MODEL_AXIS_NAME = "ionicModel"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"

AXES = (
    ionic_model_axis(
        IONIC_MODEL_AXIS_NAME,
        document=ELECTRO_PROPERTIES, scope=_SINGLE_CELL_SOLVER_COEFFS,
    ),
)

RECORD = TutorialRecord(
    name="singleCell",
    native_case_relpath="electrophysiologyProtocols/singleCell",
    axes=AXES,
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            consumes=(_BLOCK_MESH_DICT_DOCUMENT, "system/controlDict"),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES,
            ),
            produces=("postProcessing/*.txt",),
        ),
    ),
)
