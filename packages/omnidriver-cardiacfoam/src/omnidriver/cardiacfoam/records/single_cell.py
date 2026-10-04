"""``singleCell``, the single-cell tutorial record: ``electrophysiologyProtocols/singleCell``.
``blockMesh`` then ``cardiacFoam`` (``singleCellSolver``); ``ionicModel`` is the only axis.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .case_outputs import ELECTRO_PROPERTIES
from .ionic_model_axis import ionic_model_axis
from .routes import block_mesh_step, solve_step

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
        block_mesh_step((_BLOCK_MESH_DICT_DOCUMENT, "system/controlDict")),
        solve_step(("postProcessing/*.txt",)),
    ),
    serial_only=True,
)
