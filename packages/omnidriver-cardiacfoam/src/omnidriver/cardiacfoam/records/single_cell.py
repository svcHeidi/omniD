"""``singleCell``, a tutorial record (tutorials-are-pointers plan §2, step
5.1). Replaces ``cardiacfoam.tutorials.single_cell`` and its defaults module
(deleted alongside this record). Native case:
``electrophysiologyProtocols/singleCell``, a single 1x1x1 ``blockMesh`` cell
running ``myocardiumSolver singleCellSolver`` -- the same electro model
``restitutionCurves`` uses, and this record reuses that pilot's own
``ionic_model_axis`` for the same reason: both cases vary
``singleCellSolverCoeffs.ionicModel``/``singleCellStimulus.stim_amplitude``
together, and the catalog owns that pairing (``IonicModelEntry
.single_cell_stimulus_amplitude``).

**Workflow, from the native ``Allrun``** (owner rule: the record mirrors the
native commands; it does not call ``Allrun``)::

    runApplication blockMesh
    runApplication cardiacFoam
    # plotVoltage is conditional and skipped by default (CF_SKIP_PLOTS=1),
    # exactly the restitutionCurves precedent -- not one of this record's
    # steps either.

**A single cell has no mesh study.** ``system/blockMeshDict`` is one
zone-free ``hex (0 1 1) (1 1 1)`` block with no commented-out alternative
resolutions (unlike ``restitutionCurves``'s three), and neither of this
case's two committed studies (below) varies it. So this record declares no
mesh axis and no tet route -- there is nothing native to point at.

**What the case's two committed studies actually vary** (plan §2 item 2:
"declare only the axes... a study really uses"):

- ``setup/sweep_ionic_model_tissue.json``: ``ionicModel`` (this axis) and
  ``tissue`` (a direct study key, design's own "do not derive it" -- the
  same treatment ``restitutionCurves`` gives it, in the same
  ``singleCellSolverCoeffs`` scope);
- ``setup/studies/tworldVsGaur/sweep_tworld_vs_gaur.json``: ``ionicModel``,
  ``tissue``, the S1 pacing period (a direct
  ``singleCellStimulus.stim_period_S1`` key -- this case's studies never
  vary S2, so ``restitutionCurves``'s ``s1s2Protocol`` axis, which exists
  to derive ``endTime``/``writeAfterTime`` from all four S1+S2 numbers
  together, has nothing to derive here and is not reused), and
  ``outputVariables.ionic.export`` (a direct key: already catalogued,
  ``$ELECTRO_MODEL_COEFFS.outputVariables.ionic.export``).

Both native studies are rewritten onto this vocabulary in the same native
commit as this record (plan §2 item 3); see
``docs/solver-learning/cardiacfoam.md`` section SC for the dead
Python-vocabulary keys the rewrite drops and why each has no effect today.

**Every step's ``produces``/``consumes`` is observed in a real run**
(section SC, SC1-SC2): ``blockMesh`` writes exactly
:data:`~.case_outputs.POLY_MESH_OUTPUTS`; ``cardiacFoam`` writes only its
trace file(s) under ``postProcessing`` (glob, since the filename encodes
three study values: ionic model, tissue, and the stimulus protocol suffix
-- ``stimulusIO::protocolSuffix``, ``src/genericWriter/stimulusIO.C``) and,
when ``activeTensionModel`` is set (the native case's own default), a
second ``..._Ta.txt`` trace -- still inside the same glob. No
``constant/electroProperties.withDefaultValues``: like
``restitutionCurves``, ``singleCellSolver::end`` overrides
``electroModel::end`` without calling it (confirmed by this record's own
real run, section SC1), and no ``0/`` directory is created (``Vm``'s
``AUTO_WRITE`` never reaches a write time at this case's default
``endTime``/``writeInterval``).
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS
from .ionic_model_axis import ionic_model_axis

#: Like restitutionCurves: `myocardiumSolver singleCellSolver`'s own
#: `singleCellSolverCoeffs` scope, never varied by this tutorial (the
#: native case already holds it).
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
