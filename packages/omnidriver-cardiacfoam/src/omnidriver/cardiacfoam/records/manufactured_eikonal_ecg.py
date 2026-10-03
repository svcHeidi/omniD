"""``manufacturedEikonalECG``, the eikonal activation-time and template ECG manufactured-solution record.
Native case: ``manufacturedSolutions/eikonalECG``; hex, tet and two extended tet routes."""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

_TET_TEMPLATE_RELPATH = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The dimension axis takes no `solver_coefficients`: `eikonalSolverCoeffs` has
#: no `dimension` key (unlike bidomain's and bath's), so it only sets the mesh
#: step's `-dict` argument.
AXES = (
    dimension_axis("dimension", mesh_step_id="mesh"),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: `eikonalMyocardiumDomain` does not override `electroModel::end()`, so the
#: solve writes `.withDefaultValues` (unlike `singleCellSolver`).
_SOLVE_OUTPUTS = (
    WITH_DEFAULT_VALUES,
    "postProcessing/manufacturedEikonalActivationTime.dat",
    "postProcessing/eikonalECG.dat",
    "postProcessing/manufacturedEikonalECG_ECG.dat",
    "postProcessing/manufacturedEikonalECGSummary_ECG.dat",
)

# The native Allrun meshes with `blockMesh -dict system/blockMeshDict.3D`.
_MESH_STEP = block_mesh_step(
    BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict="system/blockMeshDict.3D",
)
_SOLVE_STEP = solve_step(_SOLVE_OUTPUTS, consumes=("0/activationTime",))
_WRITE_CELL_CENTRES_STEP = WorkflowStep(
    step_id="writeCellCentres",
    command=("postProcess", "-func", "writeCellCentres", "-latestTime"),
    # No `produces`: its output lands in a time directory, which cannot be
    # declared (`WorkflowStep` refuses `{`/`}`, and there is no other literal
    # path for a time-varying instance), and staging drops it regardless.
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
        _MESH_STEP, _SOLVE_STEP, *gmsh_route(_TET_TEMPLATE_RELPATH, _TET_MESH, "internal"),
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
)
