"""``manufacturedMonodomainPseudoECG``, the monodomain manufactured-solution record with pseudo-ECG output.
Native case: ``manufacturedSolutions/monodomainPseudoECG``; hex and tet routes.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

#: The `monodomainSolverCoeffs` scope, and the pseudo-ECG verifier's nested
#: echo of the tissue dimension, which the `dimension` axis keeps in step.
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)
_ECG_VERIFICATION_MODEL = ("ecgDomains", "ECG", "verificationModel")

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The native `Allrun` has no mesh step; the case's regression script meshes
#: with this dictionary.
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"

# The tet `fvSchemes` overlay is not modelled: every entry it sets already
# equals `system/fvSchemes`.
AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, _MONODOMAIN_SOLVER_COEFFS),
        ecg_verification_scope=_ECG_VERIFICATION_MODEL,
    ),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: The pseudo-ECG verifier's myocardium domain calls `electroModel::end()`, so
#: the solve writes `.withDefaultValues`.
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
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict=_MESH_DICT_DEFAULT,
        ),
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "internal"),
        solve_step(_SOLVE_OUTPUTS),
    ),
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
    },
    variant_selector="mesh",
    default_variant="hex",
)
