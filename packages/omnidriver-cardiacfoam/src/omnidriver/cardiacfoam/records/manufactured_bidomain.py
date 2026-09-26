"""``manufacturedBidomain``, a tutorial record (tutorials-are-pointers plan
§5c, step 5.4b-B).

Replaces ``cardiacfoam.tutorials.manufactured_bidomain``/``tutorials.defaults
.manufactured_bidomain`` (deleted alongside this record). The old module was
a 115-line pass-through wrapper around
``manufactured_monodomain_pseudo_ecg.make_spec`` -- every write it could
produce was really pseudo-ECG's factory writing into bidomain's own
``bidomainSolverCoeffs`` scope. This record makes those writes explicit
instead: a native case path, the axes it allows, and the workflow steps its
native case actually runs.

**The pre-processing stage (owner, 2026-09-26).** The native ``Allrun``
does not mesh at all -- serially, it is exactly::

    runApplication cardiacFoam

going straight to the solver on whatever mesh already sits in
``constant/polyMesh``. The case's own ``regression/regressionTest.sh`` is
what actually meshes it first::

    blockMesh -dict system/blockMeshDict.3D
    ./Allrun

so the mesh step's default arguments are copied from THAT script, not
invented, and ``Allrun`` itself is not changed (it is the general "solve
only, given a mesh" shape every 5.4b record shares). There is no plain
``system/blockMeshDict``, only ``.1D``/``.2D``/``.3D`` (confirmed: the
native case ships no such file) -- exactly the case
:class:`~omnidriver.core.tutorial_records.DefaultArgument` exists for (owner
Q3/Q7): the mesh step's ``-dict`` default is
``system/blockMeshDict.3D`` (matching the native default `"3D"``
``bidomainSolverCoeffs.dimension``), and the ``dimension`` axis replaces it
when a study names another dimension.

**The gmsh tet route** is declared as the record's alternative variant, the
same way the design always intended a tet case to be reachable (there is no
native ``Allrun`` tet route either -- see
:mod:`.manufactured_solution_axes`'s own module docstring for the owner's
Q8 decision and the real ``gmsh``/``gmshToFoam``/``checkMesh`` evidence).

**Every step's ``produces``/``consumes`` below is observed, not assumed**
(conformance Task 14 step 1; logged in full under "manufacturedBidomain" in
``docs/solver-learning/cardiacfoam.md``):

- a real ``blockMesh -dict system/blockMeshDict.3D`` writes exactly
  ``constant/polyMesh``'s five files (``boundary``, ``faces``,
  ``neighbour``, ``owner``, ``points``) -- the same set
  ``restitutionCurves`` observed, since bidomain's own ``blockMeshDict``
  files are each a single ``hex (`` block with no zones;
- a real ``gmsh -3 ... -setnumber lc <v>`` writes only the named ``.msh``
  file; a real ``gmshToFoam <mesh>.msh`` then writes ``constant/polyMesh``'s
  NINE entries (the five above, plus ``cellZones``, ``faceZones``,
  ``pointZones`` and ``sets/internal`` -- the template's single
  ``Physical Volume("internal")`` always becomes one cellZone/cellSet, so
  this is deterministic for this template, not a per-resolution accident);
  a real ``checkMesh`` (no ``-writeAllFields``) writes nothing but its own
  log;
- a real ``cardiacFoam`` run (hex, then tet) writes
  ``constant/electroProperties.withDefaultValues`` (``electroModel::end``,
  as every non-``singleCellSolver`` step does -- P4's R4) and exactly one
  ``postProcessing/<dim>_<N>_cells.dat`` (confirmed: ``3D_5_cells.dat`` at
  N=5 hex, ``3D_9_cells.dat`` at the tet mesh's own effective resolution) --
  never a literal path, since the verifier's own ``round(nCells^(1/d))``
  naming depends on the resolved mesh.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

#: This tutorial always addresses `myocardiumSolver bidomainSolver`'s own
#: `bidomainSolverCoeffs` scope -- never varied by this tutorial (the native
#: case already holds it, design's own "dropped... because the native case
#: already holds that value").
_BIDOMAIN_SOLVER_COEFFS = ("bidomainSolverCoeffs",)

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The mesh step's default argument, copied verbatim from
#: ``regression/regressionTest.sh``. The gmsh step has none: with no
#: ``tetNumberCells``, gmsh uses the template's own ``DefineConstant`` ``lc``
#: default (corrected 2026-09-26, review 54b M1: a ``-setnumber lc 0.1``
#: default here restated that value, and would have kept forcing it after a
#: template change).
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
