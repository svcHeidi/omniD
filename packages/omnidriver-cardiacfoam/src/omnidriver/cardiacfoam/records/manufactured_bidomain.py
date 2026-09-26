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

from .manufactured_solution_axes import dimension_axis, hex_number_cells_axis, tet_number_cells_axis

#: This tutorial always addresses `myocardiumSolver bidomainSolver`'s own
#: `bidomainSolverCoeffs` scope -- never varied by this tutorial (the native
#: case already holds it, design's own "dropped... because the native case
#: already holds that value").
_ELECTRO_DOCUMENT = "constant/electroProperties"
_BIDOMAIN_SOLVER_COEFFS = ("bidomainSolverCoeffs",)

DIMENSION_AXIS_NAME = "dimension"
NUMBER_CELLS_AXIS_NAME = "numberCells"
TET_NUMBER_CELLS_AXIS_NAME = "tetNumberCells"

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: Every step's own default-argument tokens, copied verbatim from
#: ``regression/regressionTest.sh`` (mesh) and from the module docstring's
#: real-run evidence (gmsh's own template default, ``lc=0.1``, owner Q8).
_MESH_DICT_KEY = ("-dict",)
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"
_GMSH_LC_KEY = ("-setnumber", "lc")
_GMSH_LC_DEFAULT = "0.1"

AXES = {
    DIMENSION_AXIS_NAME: dimension_axis(
        DIMENSION_AXIS_NAME,
        document=_ELECTRO_DOCUMENT, scope=_BIDOMAIN_SOLVER_COEFFS, mesh_step_id="mesh",
    ),
    NUMBER_CELLS_AXIS_NAME: hex_number_cells_axis(NUMBER_CELLS_AXIS_NAME),
    TET_NUMBER_CELLS_AXIS_NAME: tet_number_cells_axis(
        TET_NUMBER_CELLS_AXIS_NAME, gmsh_step_id="gmsh",
    ),
}

#: Real ``blockMesh``-observed outputs (module docstring); identical to
#: ``restitutionCurves``'s own, since both cases' hex ``blockMeshDict``s are
#: single, zone-free ``hex (`` blocks.
_HEX_MESH_OUTPUTS = (
    "constant/polyMesh",
    "constant/polyMesh/boundary",
    "constant/polyMesh/faces",
    "constant/polyMesh/neighbour",
    "constant/polyMesh/owner",
    "constant/polyMesh/points",
)

#: Real ``gmshToFoam``-observed outputs (module docstring): the hex set
#: above, plus the three zone files and the cellSet the template's single
#: ``Physical Volume("internal")`` always produces.
_TET_MESH_OUTPUTS = _HEX_MESH_OUTPUTS + (
    "constant/polyMesh/cellZones",
    "constant/polyMesh/faceZones",
    "constant/polyMesh/pointZones",
    "constant/polyMesh/sets/internal",
)

#: ``electroModel::end`` renames and writes this dictionary at the end of
#: every non-``singleCellSolver`` run (P4's R4) -- declared here so a restage
#: does not carry it as an unaccounted-for output (A5's exclusion needs it
#: named).
WITH_DEFAULT_VALUES = f"{_ELECTRO_DOCUMENT}.withDefaultValues"

RECORD = TutorialRecord(
    name="manufacturedBidomain",
    native_case_relpath="manufacturedSolutions/bidomain",
    allowed_axes=frozenset(AXES),
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            default_arguments=(DefaultArgument(key=_MESH_DICT_KEY, values=(_MESH_DICT_DEFAULT,)),),
            consumes=(
                "system/blockMeshDict.1D", "system/blockMeshDict.2D",
                "system/blockMeshDict.3D", "system/controlDict",
            ),
            produces=_HEX_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="gmsh",
            command=("gmsh", "-3", _TET_TEMPLATE, "-o", _TET_MESH, "-format", "msh2"),
            default_arguments=(DefaultArgument(key=_GMSH_LC_KEY, values=(_GMSH_LC_DEFAULT,)),),
            consumes=(_TET_TEMPLATE,),
            produces=(_TET_MESH,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", _TET_MESH),
            consumes=(_TET_MESH,),
            produces=_TET_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="checkMesh", command=("checkMesh",),
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", _ELECTRO_DOCUMENT,
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
)
