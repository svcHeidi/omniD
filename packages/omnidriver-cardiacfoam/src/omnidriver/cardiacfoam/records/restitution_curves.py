"""``restitutionCurves``, the S1-S2 restitution tutorial record.
Native case: ``electrophysiologyProtocols/restitutionCurves_s1s2Protocol``; ``mesh`` then ``solve``.
"""

from __future__ import annotations

from typing import Any, Sequence

from omnidriver.core.tutorial_records import TutorialRecord
from omnidriver.openfoam.axes import block_mesh_resolution_axis

from .case_outputs import ELECTRO_PROPERTIES
from .ionic_model_axis import ionic_model_axis
from .routes import block_mesh_step, solve_step
from .s1_s2_protocol_axis import s1_s2_protocol_axis

#: The `singleCellSolverCoeffs` scope of `myocardiumSolver singleCellSolver`,
#: which the native case already holds.
_SINGLE_CELL_SOLVER_COEFFS = ("singleCellSolverCoeffs",)

IONIC_MODEL_AXIS_NAME = "ionicModel"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2Protocol"
#: ``system/blockMeshDict`` documents three uniform resolutions as
#: commented-out alternatives (deltaX 0.5/0.2/0.1mm); this axis selects one.
BLOCK_MESH_RESOLUTION_AXIS_NAME = "blockMeshResolution"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"


def _explicit_cell_counts(
    cell_counts: Sequence[Any], current: tuple[int, int, int],
    extents: tuple[float, float, float] | None = None,
) -> tuple[int, int, int]:
    """The study value already is the three hex cell counts; no scaling applies."""
    del current, extents
    return tuple(cell_counts)


#: This record's own axes, each named by the name its study vocabulary uses
#: (``TutorialRecord.axes``).
AXES = (
    ionic_model_axis(
        IONIC_MODEL_AXIS_NAME,
        document=ELECTRO_PROPERTIES, scope=_SINGLE_CELL_SOLVER_COEFFS,
    ),
    s1_s2_protocol_axis(
        S1_S2_PROTOCOL_AXIS_NAME,
        electro_document=ELECTRO_PROPERTIES, scope=_SINGLE_CELL_SOLVER_COEFFS,
    ),
    block_mesh_resolution_axis(
        BLOCK_MESH_RESOLUTION_AXIS_NAME,
        documents=(_BLOCK_MESH_DICT_DOCUMENT,),
        resolution=_explicit_cell_counts,
        # The study value is the three cell counts (e.g. [40, 6, 14]), so the
        # builder's default "integer" kind does not fit; `_validate_cell_counts`
        # enforces the length of three.
        value_kind="integer_list",
    ),
)

#: A step ``consumes`` only the authored files it fails without; the solve
#: step's mesh comes from the mesh step's ``produces``.
#: ``constant/sweepCurrents`` is read by neither step (it is the
#: ``sweepCurrents`` utility's input), nor is ``system/blockMeshDict`` by
#: ``cardiacFoam``.
#:
#: The trace's name is ``<ionicModel>_<tissue>_<protocol>.txt``
#: (``singleCellSolver``'s constructor), so it depends on three study values
#: and is declared as a glob.
#:
#: No ``constant/electroProperties.withDefaultValues``: ``singleCellSolver``
#: overrides ``electroModel::end`` without calling it.

RECORD = TutorialRecord(
    name="restitutionCurves",
    native_case_relpath="electrophysiologyProtocols/restitutionCurves_s1s2Protocol",
    axes=AXES,
    workflow_steps=(
        block_mesh_step((_BLOCK_MESH_DICT_DOCUMENT, "system/controlDict")),
        solve_step(("postProcessing/*.txt",)),
    ),
)
