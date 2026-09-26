"""``restitutionCurves``, the first cardiacFOAM tutorial record (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``, step
4b -- the pilot).

Replaces ``cardiacfoam.tutorials.restitution_curves``/``tutorials.defaults
.restitution_curves`` (deleted alongside this record, once parity against
the real native case was proven -- see this package's parity evidence). The
record itself is inert data (``core.tutorial_records.TutorialRecord``): a
native case path, the axes it allows, and the workflow steps its native
``Allrun`` actually runs. It writes nothing; only an axis it names, or a
direct ``document:key`` a study supplies, ever produces a patch.

**Every write the old ``_plan_case`` made, accounted for** (design's own
instruction for this step -- "identify every write... and account for each
one: an axis, a direct study key, or dropped"), with no default overrides
supplied (``electro_property_overrides``/``physics_property_overrides``
were always ``None`` by default, so they produced no write at all and are
simply gone -- a study that wants an extra key can always name it directly):

| old write (``singleCellSolverCoeffs.``-scoped unless noted) | now |
|---|---|
| ``tissue`` | direct study key (design: "do not derive it") |
| ``ionicModel`` | ``ionicModel`` axis |
| ``singleCellStimulus.stim_amplitude`` | ``ionicModel`` axis (catalog field) |
| ``singleCellStimulus.stim_period_S1`` | ``s1s2Protocol`` axis |
| ``singleCellStimulus.nstim1`` | ``s1s2Protocol`` axis |
| ``singleCellStimulus.stim_period_S2`` | ``s1s2Protocol`` axis |
| ``singleCellStimulus.nstim2`` | ``s1s2Protocol`` axis |
| ``writeAfterTime`` | ``s1s2Protocol`` axis |
| ``system/controlDict:endTime`` | ``s1s2Protocol`` axis |

Nine writes total -- the same 9/9 the design's own §1 measurement recorded
for this tutorial's default case.

**Workflow steps, corrected against the real native ``Allrun``** (design's
own instruction: "the old DAG under-declared the mesh step; the record must
match what Allrun actually runs"). The old factory's ``workflow_dag``
declared one step, ``{"id": "solve", "command": "cardiacFoam"}`` -- but
``tutorials/electrophysiologyProtocols/restitutionCurves_s1s2Protocol
/Allrun`` unconditionally runs ``blockMesh`` first::

    runApplication blockMesh
    runApplication cardiacFoam
    if [ "${CF_SKIP_PLOTS:-1}" = "1" ]; then
        echo "Skipping plotVoltage (CF_SKIP_PLOTS=1)."
    else
        ./plotVoltage
    fi

``plotVoltage`` is conditional and SKIPPED by default (``CF_SKIP_PLOTS``
defaults to ``1`` -- the ``if`` branch that actually runs it is the
non-default one), so it is not one of this record's steps either, the same
way the old ``workflow_dag`` never ran it. This record therefore declares
exactly the two steps ``Allrun`` runs unconditionally: ``mesh``
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
#: `singleCellSolverCoeffs` scope -- never varied by this tutorial (the
#: native case already holds it; design's own "dropped... because the
#: native case already holds that value"), so both axes below are
#: instantiated with it directly rather than deriving it from a study value.
_SINGLE_CELL_SOLVER_COEFFS = ("singleCellSolverCoeffs",)

IONIC_MODEL_AXIS_NAME = "ionicModel"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2Protocol"
#: Added 2026-09-25, for the real-run regression test's coarse mesh (design
#: doc step 4c follow-up): ``system/blockMeshDict`` documents three uniform
#: resolutions as commented-out alternatives (deltaX 0.5/0.2/0.1mm; see that
#: file's own comments) -- a genuine per-case study choice this tutorial
#: never exposed before. Before this axis existed, the only way to select
#: one was a direct text edit of the staged case's ``blockMeshDict`` beside
#: the channel, exactly the pattern this whole design removes.
BLOCK_MESH_RESOLUTION_AXIS_NAME = "blockMeshResolution"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"


def _explicit_cell_counts(
    cell_counts: Sequence[Any], current: tuple[int, int, int],
    extents: tuple[float, float, float] | None = None,
) -> tuple[int, int, int]:
    """No scaling formula: this axis's study value already IS the three hex
    cell counts (one of ``system/blockMeshDict``'s own three documented
    resolutions, e.g. ``[40, 6, 14]``), taken as given -- ``current`` (the
    document's own resolution before this axis runs, P2's 2026-09-26
    addition to the axis's own ``resolution`` signature) is unused: this
    tutorial has exactly one ``blockMeshDict`` and no per-direction "stays
    1" rule to apply, so nothing here needs to read it. ``extents`` (the
    document's own physical extent, added 2026-09-26 -- see
    ``axes/block_mesh_resolution.py``'s own dated correction) is unused for
    the same reason: this axis's study value is already the target cell
    counts, not a physical cell size a formula would need the extent to
    convert.
    ``block_mesh_resolution_axis``'s own ``_validate_cell_counts`` checks the
    shape (exactly three positive integers) once ``resolution`` returns --
    this callable only turns the study's list/tuple into the plain tuple
    that check expects, inventing no formula of its own.
    """
    del current, extents
    return tuple(cell_counts)


#: This record's own axes, each named by the name its study vocabulary uses
#: (``TutorialRecord.axes``; corrected 2026-09-26, record-scoped axes: they
#: were registered into one stack-wide axis catalog).
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

#: What each step reads and writes, as observed in real runs (conformance
#: Task 14 step 1; ``docs/solver-learning/cardiacfoam.md`` R1-R4). A step
#: ``consumes`` only the authored files it fails without; the solve step's
#: mesh comes from the mesh step's ``produces``, so it is not re-declared as
#: a consumed input. ``constant/sweepCurrents`` is read by neither step
#: (R3: the ``sweepCurrents`` utility's input), nor is ``system/blockMeshDict``
#: by ``cardiacFoam``.
#:
#: The trace's name is ``<ionicModel>_<tissue>_<protocol>.txt``
#: (``singleCellSolver``'s constructor; R1 observed
#: ``BuenoOrovio_epicardialCells_S1_2000_S2_250.txt``, step 4c
#: ``TWorld_epicardialCells_S1_1000_S2_1500.txt``), so it depends on three
#: study values and is declared as a glob. ``postProcessing`` is dropped at
#: staging by the OpenFOAM layer's conventions, which A5's literal-path
#: exclusion needs for a globbed output (plan §2 item 1).
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
