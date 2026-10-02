"""``manufacturedBidomain``: the native ``Allrun`` does not mesh at all --
serially it is exactly ``runApplication cardiacFoam``, going straight to the
solver on whatever mesh already sits in ``constant/polyMesh``. The case's own
``regression/regressionTest.sh`` meshes it first with
``blockMesh -dict system/blockMeshDict.3D``, which is this record's mesh-step
default; there is no plain ``system/blockMeshDict``, only
``.1D``/``.2D``/``.3D``.

The gmsh tet route is this record's alternative variant; there is no native
``Allrun`` tet route either (see :mod:`.manufactured_solution_axes` for the
``gmsh``/``gmshToFoam``/``checkMesh`` evidence).

Every step's ``produces``/``consumes`` below is observed, not assumed (logged
under "manufacturedBidomain" in ``docs/solver-learning/cardiacfoam.md``):

- ``blockMesh -dict system/blockMeshDict.3D`` writes exactly
  ``constant/polyMesh``'s five files (``boundary``, ``faces``, ``neighbour``,
  ``owner``, ``points``): a single ``hex (`` block with no zones;
- ``gmsh -3 ... -setnumber lc <v>`` writes only the named ``.msh`` file;
  ``gmshToFoam <mesh>.msh`` then writes ``constant/polyMesh``'s nine entries
  (the five above, plus ``cellZones``, ``faceZones``, ``pointZones`` and
  ``sets/internal`` for the template's single ``Physical Volume("internal")``);
  ``checkMesh`` (no ``-writeAllFields``) writes nothing but its own log;
- ``cardiacFoam`` (hex, then tet) writes
  ``constant/electroProperties.withDefaultValues`` (``electroModel::end``, as
  every non-``singleCellSolver`` step does) and exactly one
  ``postProcessing/<dim>_<N>_cells.dat``, never a literal path: the
  verifier's own ``round(nCells^(1/d))`` naming depends on the resolved mesh.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

#: This tutorial always addresses `myocardiumSolver bidomainSolver`'s own
#: `bidomainSolverCoeffs` scope -- never varied, since the native case
#: already holds it.
_BIDOMAIN_SOLVER_COEFFS = ("bidomainSolverCoeffs",)

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The mesh step's default argument, copied verbatim from
#: ``regression/regressionTest.sh``. The gmsh step has none: with no
#: ``tetNumberCells``, gmsh uses the template's own ``DefineConstant`` ``lc``
#: default, rather than restating it and forcing it after a template change.
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"

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
