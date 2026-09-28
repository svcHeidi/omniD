"""``manufacturedEikonalECG``, a cardiacFOAM tutorial record.

Native case: ``manufacturedSolutions/eikonalECG`` -- a manufactured-solution
verification of the eikonal activation-time solve and its template ECG
calculation (see that case's own ``README.md`` for the physics). Its
``Allrun`` runs unconditionally::

    runApplication blockMesh -dict system/blockMeshDict.3D
    if [ "${1:-}" = "parallel" ]; then ...; else runApplication cardiacFoam; fi

-- serial by default (parallel is the OpenFOAM layer's concern, not a record
variant), so this record's ``hex`` route is exactly those two steps, with the
``-dict`` argument as the ``mesh`` step's own default, replaced by the
``dimension`` axis when a study picks something other than the native 3D
default.

The tet route has no native ``Allrun`` of its own: it is declared here citing
``setup/studies/tetConvergence/``'s own README and the six studies that run
it -- ``gmsh -3 <template> -setnumber lc <v>`` (evidence:
``docs/solver-learning/cardiacfoam.md`` G1-G9), then ``gmshToFoam``, then
``checkMesh``, then the same ``solve`` step. Two further routes extend it
with one extra step apiece -- ``tet-errorLocalisation``
(``postProcess -func writeCellCentres -latestTime``) and
``tet-gradientReconstruction`` (``gradientReconstructionOrder``) -- one
selector, ``variant_selector="mesh"``, with four values.

The electrode-position tables (``E1``-``E5``) are not a formula over each
``blockMeshDict``'s extents: ``E3``/``E4`` keep the same x across all three
dimensions regardless of domain size, and ``E5`` varies non-monotonically
(1D 1.65, 2D 0.18, 3D 1.55) -- these are hand-chosen sample points, the same
character as the ``R1``-``R156`` scatter the native 3D case already carries
alongside them. So they are study content: only ``cartesianConvergence`` --
the one study that actually varies ``dimension`` -- states them directly, as
five ``document:key`` overrides per case; no Python table is kept.

Workflow steps' ``produces``/``consumes`` are settled by a real run
(``docs/solver-learning/cardiacfoam.md``, section E). A real ``blockMesh``
then ``cardiacFoam`` at the coarsest resolution (10x10x10) produced exactly:
``constant/electroProperties.withDefaultValues`` (unlike ``singleCellSolver``,
``eikonalMyocardiumDomain``'s ``end()`` does not override
``electroModel::end()``, so it IS written -- R4's exemption does not hold
here) and, under ``postProcessing/``, ``manufacturedEikonalActivationTime.dat``,
``eikonalECG.dat``, ``manufacturedEikonalECG_ECG.dat`` and
``manufacturedEikonalECGSummary_ECG.dat``. The same four names reappeared
identically from a real tet run, confirming the solve step's declared
outputs hold across both mesh routes. Removing ``0/activationTime`` from a
copy of the run case made ``cardiacFoam`` fail with
``cannot find file .../0/activationTime`` (rc 1), confirming it as a real
``consumes`` entry, the way R3 established the pattern for
``restitutionCurves``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

_TET_TEMPLATE_RELPATH = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: This record's own axes. The dimension axis takes no
#: `solver_coefficients`: eikonalECG's `eikonalSolverCoeffs` has no
#: `dimension` key (unlike bidomain's and bath's `<solver>Coeffs`), so it
#: contributes the mesh step's `-dict` argument only.
AXES = (
    dimension_axis("dimension", mesh_step_id="mesh"),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: Settled by a real run (module docstring). Every cardiacFoam solve step
#: writes `.withDefaultValues` here (unlike `restitutionCurves`'s
#: `singleCellSolver`, which overrides `electroModel::end()` without calling
#: it -- see R4): `eikonalMyocardiumDomain`'s solve does call it.
_SOLVE_OUTPUTS = (
    WITH_DEFAULT_VALUES,
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
    produces=POLY_MESH_OUTPUTS,
)
_SOLVE_STEP = WorkflowStep(
    step_id="solve", command=("cardiacFoam",),
    consumes=(
        "system/controlDict", "system/fvSchemes", "system/fvSolution",
        ELECTRO_PROPERTIES, "constant/physicsProperties", "0/activationTime",
    ),
    produces=_SOLVE_OUTPUTS,
)
#: No default ``-setnumber lc``: with no ``tetNumberCells`` gmsh uses the
#: template's own ``DefineConstant`` default. ``box.msh`` is declared on both
#: sides, and ``gmshToFoam``'s full output set, from the real run through
#: this record logged in ``docs/solver-learning/cardiacfoam.md``: it includes
#: the three zone files and ``sets/internal``, not just the plain
#: ``constant/polyMesh`` files blockMesh writes.
_GMSH_STEP = WorkflowStep(
    step_id="gmsh",
    command=("gmsh", "-3", _TET_TEMPLATE_RELPATH, "-o", _TET_MESH, "-format", "msh2"),
    consumes=(_TET_TEMPLATE_RELPATH,),
    produces=(_TET_MESH,),
)
_GMSH_TO_FOAM_STEP = WorkflowStep(
    step_id="gmshToFoam", command=("gmshToFoam", _TET_MESH),
    consumes=(_TET_MESH,),
    produces=gmsh_to_foam_outputs("internal"),
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
    # A tet route's template is the 3D unit cube, so a 1D/2D `dimension` is
    # refused rather than silently ignored.
    variant_constraints={
        variant: {"dimension": TET_DIMENSIONS}
        for variant in ("tet", "tet-errorLocalisation", "tet-gradientReconstruction")
    },
)
