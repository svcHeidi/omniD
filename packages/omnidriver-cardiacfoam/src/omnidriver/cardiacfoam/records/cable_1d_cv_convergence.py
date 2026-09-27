"""``cable1DCVConvergence``, a tutorial record (tutorials-are-pointers plan
§5e, step 5.3). Native case: the same
``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV`` step 5.2's
``cable1DRestitution`` points at (§5e: "5.3 needs 5.2 -- same native case
``cableProtocol``").

Replaces ``cardiacfoam.tutorials.cable_1d_cv_convergence``/``tutorials
.defaults.cable_1d_cv_convergence`` (deleted alongside this record).

**Every write the old ``_plan_case`` made, accounted for:**

| old write | now |
|---|---|
| ``system/blockMeshDict`` hex block rewrite | ``dx`` axis, shared with ``cable1DRestitution`` (:mod:`.cable_axes`) |
| ``system/controlDict:deltaT``/``endTime`` | direct study keys, in seconds |
| ``monodomainSolverCoeffs.conductivity``/``tissue``/``ionicModel``/``solutionAlgorithm`` | direct study keys (no catalog-derived axis: this tutorial's stimulus is not the ionic-model catalog's single-cell amplitude) |
| ``monodomainSolverCoeffs.externalStimulus`` | direct study key, stated as one mapping value (owner decision: "its study states its own ``externalStimulus`` explicitly") -- unlike ``cable1DRestitution``, this tutorial derives no S1-S2 schedule: a convergence sweep launches one wave and measures its speed |
| ``conductivity_id``, ``case_dir_name``/``setup_dir_name``/``output_dir_name``, ``postprocess_strict_artifacts`` | dropped: sweep-engine/staging bookkeeping the new engine already provides |
| ``electro_property_overrides``/``physics_property_overrides`` | dropped: always ``None`` in the real committed study |
| ``parallel`` (old default ``True``) | dropped: owner Q6, serial is the record's default |

No post-processing step: the old ``make_spec``'s own ``workflow_dag`` had
none either (``expected_artifacts: []``) -- CV extraction
(``setup/extract_cv.py``) is a manual script the native ``run_convergence.sh``
drives directly, never wired through ``Allrun``/``Allrun.post``, so it is
not one of this record's steps either (the same "the record mirrors
``Allrun``" rule that excludes ``restitutionCurves``'s conditional
``plotVoltage``).

**Workflow steps, from the native ``Allrun``**::

    runApplication blockMesh
    runApplication cardiacFoam

(the ``parallel`` branch is owner Q6, the OpenFOAM layer's job).

Produces/consumes observed in a real run:
``docs/solver-learning/cardiacfoam.md``, section "cable".
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
