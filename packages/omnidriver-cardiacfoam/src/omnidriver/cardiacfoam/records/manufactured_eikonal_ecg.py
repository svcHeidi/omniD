"""``manufacturedEikonalECG``, a cardiacFOAM tutorial record (plan
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5c, task 5.4b-E). Replaces
``cardiacfoam.tutorials.manufactured_eikonal_ecg``/``tutorials.defaults
.manufactured_eikonal_ecg`` (deleted alongside this record).

Native case: ``manufacturedSolutions/eikonalECG`` -- a manufactured-solution
verification of the eikonal activation-time solve and its template ECG
calculation (that case's own ``README.md`` has the physics). Its ``Allrun``
runs unconditionally::

    runApplication blockMesh -dict system/blockMeshDict.3D
    if [ "${1:-}" = "parallel" ]; then ...; else runApplication cardiacFoam; fi

-- serial by default (owner Q6: parallel is the OpenFOAM layer's concern, not
a record variant), so this record's ``hex`` route is exactly those two steps,
with the ``-dict`` argument as the ``mesh`` step's own
:class:`~omnidriver.core.tutorial_records.DefaultArgument`, replaced by the
``dimension`` axis when a study picks something other than the native 3D
default (owner Q2/Q3, "blockMesh is always the default, gmsh is an optional
extra mesher").

**The tet route has no native ``Allrun`` of its own** (owner Q7/Q8): it is
declared here citing ``setup/studies/tetConvergence/``'s own README and the
six studies that run it, exactly as ``regressionTest.sh``/the studies compose
it today -- ``gmsh -3 <template> -setnumber lc <v>`` (evidence:
``docs/solver-learning/cardiacfoam.md`` G1-G9; the native template already
carries ``DefineConstant[ lc = {0.1, Name "lc"} ]``, commit ``60805b27``),
then ``gmshToFoam``, then ``checkMesh``, then the same ``solve`` step. Two
further routes extend it with one extra step apiece --
``tet-errorLocalisation`` (``postProcess -func writeCellCentres -latestTime``)
and ``tet-gradientReconstruction`` (``gradientReconstructionOrder``, already
authorized in ``command_authorization.CARDIAC_AUXILIARY_COMMANDS``) -- one
selector, ``variant_selector="mesh"``, with four values, because a record has
one selector (design's own rule).

**Every write the old ``_apply_case``/``_plan_case`` made, accounted for**
(this package's own accounting convention, ``restitution_curves.py``'s
pattern):

| old write | now |
|---|---|
| ``eikonalSolverCoeffs.verificationModel.type`` | direct study key (never varied by any of the six studies; native case already holds ``manufacturedEikonalVerifier``) |
| ``ecgDomains.ECG.ecgSolver``/``verificationModel.enabled``/``referenceQuadratureOrder``/``checkQuadratureOrders`` | direct study keys (never varied; native case already holds them) |
| ``eikonalSolverCoeffs.conductivity`` | direct study key (``nonlinearControl``/``tetConvergence``) |
| ``eikonalSolverCoeffs.eikonalAdvectionDiffusionApproach`` | direct study key (``nonlinearControl``/``tetConvergence``) |
| ``ecgDomains.ECG.electrodePositions.<E1-E5>`` | direct study keys (``cartesianConvergence`` only -- see below; no formula reproduces them) |
| block-mesh resolution (hex) | ``numberCells`` axis |
| gmsh ``__LC__``/``render_tet_geo`` (tet) | ``tetNumberCells`` axis (the template takes ``lc`` via CLI now, natively, so there is nothing left to render) |
| ``grad_scheme`` | direct study key, ``system/fvSchemes:gradSchemes.default`` |
| ``fv_scheme_overrides``/``fv_solution_overrides`` | direct study keys (``system/fvSchemes``/``system/fvSolution`` are OpenFOAM-owned, accepted unvalidated) |
| ``numerics_profile`` | dropped: its one profile (``eikonal_tet``) copied a tet ``fvSolution`` overlay that was byte-identical to the case's own ``system/fvSolution`` (owner Q10; the overlay is deleted natively) |
| ``conductivity_label`` | dropped (naming only; case content is unaffected) |
| ``mesh_family``/``dimensions``/``solver_types`` | the ``mesh`` variant selector plus the ``dimension`` axis (``solver_types`` was always ``["eikonal"]``, no second solver ever existed) |

**The electrode-position formula question (owner Q7's "First check whether a
formula... reproduces them").** The native 3D ``electrodePositions``
(``E1``-``E5``) equal the old module's own 3D table exactly (byte for byte,
compared against the real native ``constant/electroProperties``) -- but the
1D/2D/3D tables are not a formula over each ``blockMeshDict``'s extents:
``E3``/``E4`` keep the SAME x across all three dimensions regardless of
domain size, and ``E5`` varies non-monotonically (1D 1.65, 2D 0.18, 3D
1.55) -- these are hand-chosen sample points, the same character as the
``R1``-``R156`` scatter the native 3D case already carries alongside them,
not a derived quantity. So they are STUDY CONTENT (owner Q7's other branch):
only ``cartesianConvergence`` -- the one study that actually varies
``dimension`` -- states them directly, as five ``document:key`` overrides
per case; no Python table is kept.

**Workflow steps' ``produces``/``consumes``, settled by a real run**
(``docs/solver-learning/cardiacfoam.md``, section E; §1's "a claim about
what a step reads or writes is settled by a real run"). A real ``blockMesh``
then ``cardiacFoam`` at the coarsest resolution (10x10x10) produced exactly:
``constant/electroProperties.withDefaultValues`` (unlike ``singleCellSolver``,
``eikonalMyocardiumDomain``'s ``end()`` does not override ``electroModel
::end()``, so it IS written -- R4's exemption does not hold here) and, under
``postProcessing/``, ``manufacturedEikonalActivationTime.dat``,
``eikonalECG.dat``, ``manufacturedEikonalECG_ECG.dat`` and
``manufacturedEikonalECGSummary_ECG.dat``. The same four ``postProcessing``
names (plus ``.withDefaultValues``) reappeared identically from a real tet
run (``gmsh``/``gmshToFoam``/``checkMesh``/``cardiacFoam``), confirming the
solve step's declared outputs hold across both mesh routes. Removing
``0/activationTime`` from a copy of the run case made ``cardiacFoam`` fail
with ``cannot find file .../0/activationTime`` (rc 1), confirming it as a
real ``consumes`` entry the way R3 established the pattern for
``restitutionCurves``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, GMSH_LC_KEY, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

_ELECTRO_DOCUMENT = "constant/electroProperties"
_TET_TEMPLATE_RELPATH = "setup/studies/tetConvergence/box.geo.template"

#: This record's own axes. The dimension axis takes no
#: `solver_coefficients`: eikonalECG's `eikonalSolverCoeffs` has no
#: `dimension` key (unlike bidomain's and bath's `<solver>Coeffs`), so it
#: contributes the mesh step's `-dict` argument only.
AXES = (
    dimension_axis("dimension", mesh_step_id="mesh"),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: Settled by a real run (module docstring; ``docs/solver-learning
#: /cardiacfoam.md`` section E). Shared by the ``mesh`` (blockMesh) and
#: ``gmshToFoam`` steps: whichever mesher ran, the mesh route produces the
#: same `constant/polyMesh` files.
_MESH_OUTPUTS = (
    "constant/polyMesh",
    "constant/polyMesh/boundary",
    "constant/polyMesh/faces",
    "constant/polyMesh/neighbour",
    "constant/polyMesh/owner",
    "constant/polyMesh/points",
)

#: Settled by a real run (module docstring). Every cardiacFoam solve step
#: writes `.withDefaultValues` here (unlike `restitutionCurves`'s
#: `singleCellSolver`, which overrides `electroModel::end()` without calling
#: it -- see R4): `eikonalMyocardiumDomain`'s solve does call it.
_SOLVE_OUTPUTS = (
    "constant/electroProperties.withDefaultValues",
    "postProcessing/manufacturedEikonalActivationTime.dat",
    "postProcessing/eikonalECG.dat",
    "postProcessing/manufacturedEikonalECG_ECG.dat",
    "postProcessing/manufacturedEikonalECGSummary_ECG.dat",
)

_MESH_STEP = WorkflowStep(
    step_id="mesh", command=("blockMesh",),
    default_arguments=(
        DefaultArgument(key=MESH_DICT_KEY, values=("system/blockMeshDict.3D",)),
    ),
    consumes=BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",),
    produces=_MESH_OUTPUTS,
)
_SOLVE_STEP = WorkflowStep(
    step_id="solve", command=("cardiacFoam",),
    consumes=(
        "system/controlDict", "system/fvSchemes", "system/fvSolution",
        _ELECTRO_DOCUMENT, "constant/physicsProperties", "0/activationTime",
    ),
    produces=_SOLVE_OUTPUTS,
)
_GMSH_STEP = WorkflowStep(
    step_id="gmsh",
    command=("gmsh", "-3", _TET_TEMPLATE_RELPATH, "-o", "box.msh", "-format", "msh2"),
    default_arguments=(
        DefaultArgument(key=GMSH_LC_KEY, values=("0.1",)),
    ),
    consumes=(_TET_TEMPLATE_RELPATH,),
)
_GMSH_TO_FOAM_STEP = WorkflowStep(
    step_id="gmshToFoam", command=("gmshToFoam", "box.msh"),
    produces=_MESH_OUTPUTS,
)
_CHECK_MESH_STEP = WorkflowStep(step_id="checkMesh", command=("checkMesh",))
_WRITE_CELL_CENTRES_STEP = WorkflowStep(
    step_id="writeCellCentres",
    command=("postProcess", "-func", "writeCellCentres", "-latestTime"),
    # No `produces`: its output lands in a time directory, which cannot be
    # declared (`WorkflowStep` refuses `{`/`}`, and there is no other literal
    # path for a time-varying instance) -- and it is dropped at staging
    # regardless (A2a's `instance_directory_pattern`).
)
_GRADIENT_RECONSTRUCTION_STEP = WorkflowStep(
    step_id="gradientReconstructionOrder", command=("gradientReconstructionOrder",),
    consumes=("system/fvSchemes",),
)

RECORD = TutorialRecord(
    name="manufacturedEikonalECG",
    native_case_relpath="manufacturedSolutions/eikonalECG",
    axes=AXES,
    workflow_steps=(
        _MESH_STEP, _SOLVE_STEP, _GMSH_STEP, _GMSH_TO_FOAM_STEP, _CHECK_MESH_STEP,
        _WRITE_CELL_CENTRES_STEP, _GRADIENT_RECONSTRUCTION_STEP,
    ),
    variant_selector="mesh",
    default_variant="hex",
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
        "tet-errorLocalisation": ("gmsh", "gmshToFoam", "checkMesh", "solve", "writeCellCentres"),
        "tet-gradientReconstruction": (
            "gmsh", "gmshToFoam", "checkMesh", "solve", "gradientReconstructionOrder",
        ),
    },
    # Review 54b I3: a tet route's template is the 3D unit cube, so a 1D/2D
    # `dimension` is refused rather than silently ignored.
    variant_constraints={
        variant: {"dimension": TET_DIMENSIONS}
        for variant in ("tet", "tet-errorLocalisation", "tet-gradientReconstruction")
    },
)
