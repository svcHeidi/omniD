"""``manufacturedMonodomainPseudoECG``, a cardiacFOAM tutorial record (plan
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5c, task 5.4b-P, last in 5.4b). Replaces
``cardiacfoam.tutorials.manufactured_monodomain_pseudo_ecg``/``tutorials
.defaults.manufactured_monodomain_pseudo_ecg`` (deleted alongside this
record).

Native case: ``manufacturedSolutions/monodomainPseudoECG`` -- a
manufactured-solution verification of the monodomain stack with pseudo-ECG
electrode output (that case's own ``README.md`` has the physics). Its
``Allrun`` does not mesh at all (owner Q7, the same gap bidomain's own
record found): serially it is exactly::

    runApplication cardiacFoam

going straight to the solver on whatever mesh already sits in
``constant/polyMesh``. The case's own ``regression/regressionTest.sh`` is
what actually meshes it first::

    blockMesh -dict system/blockMeshDict.3D
    ./Allrun parallel

so the mesh step's default argument is copied from THAT script (owner
Q2/Q3), and ``Allrun`` itself is not changed. There is no plain
``system/blockMeshDict``, only ``.1D``/``.2D``/``.3D``.

**The gmsh tet route** has no native ``Allrun`` either (owner Q7/Q8): it is
declared here citing ``setup/studies/tetConvergence/``'s own README and the
two studies that run it (``tetConvergence``, ``tetTemporalControl``) --
``gmsh -3 <template> -setnumber lc <v>`` (the template already carries
``DefineConstant[ lc = {0.1, Name "lc"} ]``, native ``21f7bc82e``), then
``gmshToFoam``, then ``checkMesh``, then the same ``solve`` step.

**The ``dimension`` axis models a two-key relation.** The native case
echoes the tissue dimension into the pseudo-ECG verifier's own dimension
(``monodomainSolverCoeffs.dimension`` AND
``monodomainSolverCoeffs.ecgDomains.ECG.verificationModel.dimension`` are
both ``"3D"``), so :func:`.manufactured_solution_axes.dimension_axis`'s
``ecg_verification_scope`` keeps them together: one study value drives both
keys, the same way the axis already drives the mesh step's ``-dict``
argument. This is the relation the plan names ("sets
``monodomainSolverCoeffs.dimension`` and ``ecgDomains.ECG.dimension``
together").

**The tet ``fvSchemes`` overlay is a no-op, settled by a real run (not
migrated).** ``setup/studies/tetConvergence/fvSchemes`` is not byte-identical
to ``system/fvSchemes`` (owner Q10 only deletes byte-identical overlays; this
one differs in header/formatting/comments), so it was not deleted natively.
But every scheme entry it sets (``ddtSchemes.default none``,
``ddtSchemes.ddt(Vm) backward``, ``gradSchemes.default leastSquares``,
``divSchemes.default none``, ``laplacianSchemes.default Gauss linear
corrected``, ``interpolationSchemes.default linear``,
``snGradSchemes.default corrected``) already equals ``system/fvSchemes``'s
own value -- confirmed by a real tet run (docstring evidence below, PE3)
against the case's own ``system/fvSchemes`` with no overlay swap: the
manufactured-solution error table came out at the expected order of
magnitude for the coarser tet mesh. The old ``_NUMERICS_PROFILES =
{"monodomain_tet": ("fvSchemes", "fvSolution")}``/``shutil.copy`` swap this
case's own ``_apply_case`` performed is therefore not modelled here: the tet
route declares no extra step and reads ``system/fvSchemes`` directly, the
same as bidomain's and eikonalECG's tet routes (neither has an overlay file
at all). The overlay file itself is a native quirk, left alone.

**Every write the old ``_apply_case``/``_plan_case`` made, accounted for**
(this package's own accounting convention):

| old write | now |
|---|---|
| ``monodomainSolverCoeffs.dimension`` + mesh ``-dict`` | ``dimension`` axis |
| ``monodomainSolverCoeffs.ecgDomains.ECG.verificationModel.dimension`` | the same ``dimension`` axis (``ecg_verification_scope``) |
| ``monodomainSolverCoeffs.verificationModel.type`` | direct study key (native default is ``manufacturedAnisotropicMonodomainVerifier``; the Python default, ``manufacturedFDAMonodomainVerifier``, is deleted -- a study that wants FDA now states it) |
| ``monodomainSolverCoeffs.conductivity`` | direct study key |
| ``ecgDomains.ECG.ecgSolver``/``verificationModel.enabled`` | dropped: never varied by any of the 4 studies (``ecg_enabled`` was always ``True``), and the native case already holds ``pseudoECG``/``yes`` |
| ``ecgDomains.ECG.verificationModel.anisotropic`` | direct study key, one value per case, matching ``verificationModel.type`` row for row (catalog validation refuses a mismatch by name, owner Q11 -- this is the check, not a second derivation) |
| ``ecgDomains.ECG.verificationModel.referenceQuadratureOrder``/``checkQuadratureOrders`` | dropped: never varied; native already holds ``96``/``(6 12 24 48)`` |
| ``ecgDomains.ECG.electrodePositions.<E1-E5>`` | direct study keys, in the two studies that vary ``dimension`` (``cartesianConvergence``, ``temporalConvergence``) -- the 1D/2D/3D 5-point ``E1``-``E5`` tables the old defaults held. ``R1``-``R156`` (3D-only, in the old defaults' 3D table) are dropped everywhere: the old code wrote them only as a no-op `ensure` of the native file's own already-identical values (upsert semantics never remove a key either, so a 1D/2D case kept them unused but present regardless) -- writing or not writing them produces byte-identical case content, so nothing restates them |
| block-mesh resolution (hex) | ``numberCells`` axis |
| gmsh ``__LC__``/``render_tet_geo`` (tet) | ``tetNumberCells`` axis (the template takes ``lc`` via CLI now; nothing left to render) |
| ``grad_scheme`` | direct study key, ``system/fvSchemes:gradSchemes.default`` |
| ``end_time`` | direct study key, ``system/controlDict:endTime`` |
| ``numerics_profile`` | dropped (see above: its one profile's overlay is a no-op) |
| ``phi_tolerance`` | dropped: never appears in any of the 4 committed studies (it is a bidomain-only key; ``bidomainSolverCoeffs`` has no monodomain equivalent) |
| ``ecg_enabled``/``piecewise_sweep``/``mesh_family``/``dimensions``/``solver_types``/``run_in_parallel`` | dropped: the sweep JSON's own zip/variant-selector vocabulary and Q6 (serial only) replace them |
| ``conductivity_label`` (n/a here; eikonalECG only) | -- |

**Workflow steps' ``produces``/``consumes``, settled by a real run**
(``docs/solver-learning/cardiacfoam.md``, section PE). ``blockMesh -dict
system/blockMeshDict.3D`` then ``cardiacFoam`` at ``(5 5 5)`` (edited down
from the native ``(20 20 20)`` for a fast run) wrote exactly:
``constant/electroProperties.withDefaultValues`` (this solve step does call
``electroModel::end()``, unlike ``restitutionCurves``'s ``singleCellSolver``,
R4), ``postProcessing/3D_5_cells.dat``, ``postProcessing/pseudoECG.dat``,
``postProcessing/manufacturedPseudoECG_ECG.dat`` and
``postProcessing/manufacturedPseudoECGSummary_ECG.dat`` -- exactly the five
the brief predicted from the C++, confirmed rather than assumed. A real
``gmsh``/``gmshToFoam``/``checkMesh``/``cardiacFoam`` tet run (``lc=0.3``,
706 elements) reproduced the same five names (``postProcessing/3D_7_cells
.dat`` at that mesh's own effective resolution), with no ``fvSchemes``
overlay swap (see above). Neither route ships or reads a ``0/`` directory:
the manufactured initial condition is computed by the solver itself, the
same shape bidomain's own record already established.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

#: This tutorial's own `monodomainSolverCoeffs` scope, and the pseudo-ECG
#: verifier's own nested echo of the tissue dimension (owner Q11's
#: relation: `ecgDomains.ECG.verificationModel.anisotropic` must agree with
#: `verificationModel.type`; this axis keeps `verificationModel.dimension`
#: in step with the tissue `dimension` the same way).
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)
_ECG_VERIFICATION_MODEL = ("ecgDomains", "ECG", "verificationModel")

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The mesh step's default argument, copied verbatim from
#: `regression/regressionTest.sh` (there is no native `Allrun` mesh step at
#: all -- owner Q7, the same gap bidomain's record found).
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"

AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, _MONODOMAIN_SOLVER_COEFFS),
        ecg_verification_scope=_ECG_VERIFICATION_MODEL,
    ),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: Settled by a real run (module docstring, PE1/PE3): every cardiacFoam
#: solve step here writes `.withDefaultValues` (the pseudo-ECG verifier's
#: myocardium domain does call `electroModel::end()`).
_SOLVE_OUTPUTS = (
    WITH_DEFAULT_VALUES,
    "postProcessing/*_cells.dat",
    "postProcessing/pseudoECG.dat",
    "postProcessing/manufacturedPseudoECG_ECG.dat",
    "postProcessing/manufacturedPseudoECGSummary_ECG.dat",
)

RECORD = TutorialRecord(
    name="manufacturedMonodomainPseudoECG",
    native_case_relpath="manufacturedSolutions/monodomainPseudoECG",
    axes=AXES,
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            default_arguments=(DefaultArgument(key=MESH_DICT_KEY, values=(_MESH_DICT_DEFAULT,)),),
            consumes=BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="gmsh",
            command=("gmsh", "-3", _TET_TEMPLATE, "-o", _TET_MESH, "-format", "msh2"),
            consumes=(_TET_TEMPLATE,),
            produces=(_TET_MESH,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", _TET_MESH),
            consumes=(_TET_MESH,),
            produces=gmsh_to_foam_outputs("internal"),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES,
            ),
            produces=_SOLVE_OUTPUTS,
        ),
    ),
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
    },
    variant_selector="mesh",
    default_variant="hex",
    variant_constraints={"tet": {"dimension": TET_DIMENSIONS}},
)
