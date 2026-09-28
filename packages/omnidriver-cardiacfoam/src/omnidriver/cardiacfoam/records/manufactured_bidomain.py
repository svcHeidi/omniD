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

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

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
        WorkflowStep(
            step_id="checkMesh", command=("checkMesh",),
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES,
            ),
            produces=(WITH_DEFAULT_VALUES, "postProcessing/*_cells.dat"),
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
