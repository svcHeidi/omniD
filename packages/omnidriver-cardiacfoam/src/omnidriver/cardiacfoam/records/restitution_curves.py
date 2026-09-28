"""``restitutionCurves``, the first cardiacFOAM tutorial record.

The record itself is inert data (``core.tutorial_records.TutorialRecord``): a
native case path, the axes it allows, and the workflow steps its native
``Allrun`` actually runs. It writes nothing; only an axis it names, or a
direct ``document:key`` a study supplies, ever produces a patch.

``tutorials/electrophysiologyProtocols/restitutionCurves_s1s2Protocol/Allrun``
unconditionally runs::

    runApplication blockMesh
    runApplication cardiacFoam
    if [ "${CF_SKIP_PLOTS:-1}" = "1" ]; then
        echo "Skipping plotVoltage (CF_SKIP_PLOTS=1)."
    else
        ./plotVoltage
    fi

``plotVoltage`` is conditional and skipped by default (``CF_SKIP_PLOTS``
defaults to ``1``), so it is not one of this record's steps. This record
declares exactly the two steps ``Allrun`` runs unconditionally: ``mesh``
(``blockMesh``) then ``solve`` (``cardiacFoam``).
"""

from __future__ import annotations

from typing import Any, Sequence

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from omnidriver.openfoam.axes import block_mesh_resolution_axis

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS
from .ionic_model_axis import ionic_model_axis
from .s1_s2_protocol_axis import s1_s2_protocol_axis

#: This tutorial always addresses `myocardiumSolver singleCellSolver`'s own
#: `singleCellSolverCoeffs` scope -- never varied by this tutorial, since the
#: native case already holds it -- so both axes below are instantiated with
#: it directly rather than deriving it from a study value.
_SINGLE_CELL_SOLVER_COEFFS = ("singleCellSolverCoeffs",)

IONIC_MODEL_AXIS_NAME = "ionicModel"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2Protocol"
#: ``system/blockMeshDict`` documents three uniform resolutions as
#: commented-out alternatives (deltaX 0.5/0.2/0.1mm; see that file's own
#: comments) -- a genuine per-case study choice. Without this axis, the only
#: way to select one is a direct text edit of the staged case's
#: ``blockMeshDict``.
BLOCK_MESH_RESOLUTION_AXIS_NAME = "blockMeshResolution"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"


def _explicit_cell_counts(
    cell_counts: Sequence[Any], current: tuple[int, int, int],
    extents: tuple[float, float, float] | None = None,
) -> tuple[int, int, int]:
    """No scaling formula: this axis's study value already IS the three hex
    cell counts (one of ``system/blockMeshDict``'s own three documented
    resolutions, e.g. ``[40, 6, 14]``), taken as given. ``current`` is
    unused: this tutorial has exactly one ``blockMeshDict`` and no
    per-direction "stays 1" rule to apply. ``extents`` is unused for the same
    reason: this axis's study value is already the target cell counts, not a
    physical cell size a formula would need the extent to convert.
    ``block_mesh_resolution_axis``'s own ``_validate_cell_counts`` checks the
    shape (exactly three positive integers) once ``resolution`` returns --
    this callable only turns the study's list/tuple into the plain tuple
    that check expects, inventing no formula of its own.
    """
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
        # The study value is already the three cell counts (e.g.
        # [40, 6, 14]), not a bare count a formula expands -- "integer" (this
        # builder's default) does not fit a list; "integer_list" is the
        # closest existing `contracts.dictionary.VALUE_KINDS` member for "a
        # list of ints" (no fixed-length-3 kind exists, and none is added
        # here: `_validate_cell_counts` already enforces exactly three
        # positive integers once `resolution` returns).
        value_kind="integer_list",
    ),
)

#: What each step reads and writes, as observed in real runs
#: (``docs/solver-learning/cardiacfoam.md`` R1-R4). A step ``consumes`` only
#: the authored files it fails without; the solve step's mesh comes from the
#: mesh step's ``produces``, so it is not re-declared as a consumed input.
#: ``constant/sweepCurrents`` is read by neither step (R3: the
#: ``sweepCurrents`` utility's input), nor is ``system/blockMeshDict`` by
#: ``cardiacFoam``.
#:
#: The trace's name is ``<ionicModel>_<tissue>_<protocol>.txt``
#: (``singleCellSolver``'s constructor; R1 observed
#: ``BuenoOrovio_epicardialCells_S1_2000_S2_250.txt``), so it depends on
#: three study values and is declared as a glob. ``postProcessing`` is
#: dropped at staging by the OpenFOAM layer's conventions.
#:
#: No ``constant/electroProperties.withDefaultValues``: ``singleCellSolver``
#: overrides ``electroModel::end`` without calling it, and no real run of
#: this case writes one (R4). The mesh step's outputs are
#: ``case_outputs.POLY_MESH_OUTPUTS`` (R1).

RECORD = TutorialRecord(
    name="restitutionCurves",
    native_case_relpath="electrophysiologyProtocols/restitutionCurves_s1s2Protocol",
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
