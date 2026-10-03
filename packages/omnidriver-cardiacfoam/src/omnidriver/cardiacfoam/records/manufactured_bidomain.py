"""``manufacturedBidomain``, the bidomain manufactured-solution record.
Native case: ``manufacturedSolutions/bidomain``; hex and tet routes."""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

#: The `bidomainSolverCoeffs` scope of `myocardiumSolver bidomainSolver`, which
#: the native case already holds.
_BIDOMAIN_SOLVER_COEFFS = ("bidomainSolverCoeffs",)

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The native Allrun does not mesh; the case's regression script meshes with
#: this dictionary. The gmsh step has no default: with no
#: ``tetNumberCells``, gmsh uses the template's own ``DefineConstant`` ``lc``
#: default, rather than restating it and forcing it after a template change.
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"

# `blockMesh` writes the five `polyMesh` files; `gmshToFoam` adds the zone and
# set files for the template's single Physical Volume. The solve writes exactly
# one `<dim>_<N>_cells.dat`, whose name the verifier derives from the resolved
# mesh, so it is declared as a glob.
AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, _BIDOMAIN_SOLVER_COEFFS),
    ),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

RECORD = TutorialRecord(
    name="manufacturedBidomain",
    native_case_relpath="manufacturedSolutions/bidomain",
    axes=AXES,
    workflow_steps=(
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict=_MESH_DICT_DEFAULT,
        ),
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "internal"),
        solve_step((WITH_DEFAULT_VALUES, "postProcessing/*_cells.dat")),
    ),
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
    },
    variant_selector="mesh",
    default_variant="hex",
)
