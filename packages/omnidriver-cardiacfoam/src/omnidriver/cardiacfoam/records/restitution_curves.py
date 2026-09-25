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

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .ionic_model_axis import ionic_model_axis
from .s1_s2_protocol_axis import s1_s2_protocol_axis

#: This tutorial always addresses `myocardiumSolver singleCellSolver`'s own
#: `singleCellSolverCoeffs` scope -- never varied by this tutorial (the
#: native case already holds it; design's own "dropped... because the
#: native case already holds that value"), so both axes below are
#: instantiated with it directly rather than deriving it from a study value.
_ELECTRO_DOCUMENT = "constant/electroProperties"
_SINGLE_CELL_SOLVER_COEFFS = ("singleCellSolverCoeffs",)

IONIC_MODEL_AXIS_NAME = "ionicModel"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2Protocol"

#: This record's own axis instances, keyed by the name its study vocabulary
#: uses -- registered into the cardiac stack's axis catalog by
#: ``records/__init__.py``, alongside every other record's own axes.
AXES = {
    IONIC_MODEL_AXIS_NAME: ionic_model_axis(
        IONIC_MODEL_AXIS_NAME,
        document=_ELECTRO_DOCUMENT, scope=_SINGLE_CELL_SOLVER_COEFFS,
    ),
    S1_S2_PROTOCOL_AXIS_NAME: s1_s2_protocol_axis(
        S1_S2_PROTOCOL_AXIS_NAME,
        electro_document=_ELECTRO_DOCUMENT, scope=_SINGLE_CELL_SOLVER_COEFFS,
    ),
}

RECORD = TutorialRecord(
    name="restitutionCurves",
    native_case_relpath="electrophysiologyProtocols/restitutionCurves_s1s2Protocol",
    allowed_axes=frozenset(AXES),
    workflow_steps=(
        WorkflowStep(step_id="mesh", command=("blockMesh",)),
        WorkflowStep(step_id="solve", command=("cardiacFoam",)),
    ),
)
