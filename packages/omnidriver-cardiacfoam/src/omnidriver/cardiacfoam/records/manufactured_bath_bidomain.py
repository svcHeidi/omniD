"""``manufacturedBathBidomain``, a tutorial record (tutorials-are-pointers plan
§5b, step 5.4a).

Replaces ``cardiacfoam.tutorials.manufactured_bath_bidomain`` and its defaults
module (deleted alongside this record). Native case:
``manufacturedSolutions/bathBidomain``, the FDA bidomain-with-bath
manufactured solution (that case's ``README.md`` has the physics).

**The pre-processing stage (owner, 2026-09-26).** The native ``Allrun`` runs,
serially (owner Q6: parallel is the OpenFOAM layer's concern)::

    DIM=${1:-1D}
    runApplication blockMesh -dict system/blockMeshDict.${DIM}
    runApplication topoSet
    runApplication setTorsoOrganConductivityField
    runApplication cardiacFoam

and its ``regression/regressionTest.sh`` runs that ``Allrun`` on
``system/blockMeshDict.1D``, matching the case's own ``dimension "1D"``. So
the ``hex`` route is those four steps, with ``-dict system/blockMeshDict.1D``
as the mesh step's :class:`~omnidriver.core.tutorial_records.DefaultArgument`,
which the ``dimension`` axis replaces. Each of the three ``blockMeshDict.<dim>``
files has three ``hex (`` blocks (left bath, myocardium, right bath), so
``numberCells`` is built with ``expected_blocks=3``.

**The tet route** has no native ``Allrun``; it is the route the case's tet
studies run (``setup/studies/tetConvergence/three_domain_box.geo.template``,
which ``Allclean`` also cleans up after): ``gmsh`` on the template, then
``gmshToFoam``, ``checkMesh``, ``setTorsoOrganConductivityField``, the solve,
and ``bathBidomainInterfaceMetrics -latestTime``. No ``topoSet``: the
template's ``Physical Volume("myocardium")``/``("bath")`` already become the
two cellZones. The gmsh step carries no ``-setnumber lc`` default: without
one gmsh uses the template's own ``DefineConstant`` default, and the
``tetNumberCells`` axis appends ``-setnumber lc <1/N>`` (review 54b M1).

**What a study states directly, not through an axis:**

- the FDA boundary variant. ``electrodePair`` is the native state. A
  ``groundElectrode`` study sets ``verificationModel.fdaBathVariant`` and
  replaces ``bathPotentialDomain.groundPatches``/``surfaceCurrentPatches`` as
  whole dictionaries (owner Q4, 2026-09-26: the case writer replaces a
  sub-dictionary rather than merging into it, observed on the real file and
  logged as BB4 in ``docs/solver-learning/cardiacfoam.md``). The C++
  (``extracellularPotentialDomain.C``) is fatal on a patch listed in both;
- ``phiERefPoint`` is the native case's ``(-0.9 0.05 0.05)`` (owner Q5); a
  study that needs another states it. The old module's half-cell shift
  existed only for parallel runs, and records run serial.

**Every step's ``produces``/``consumes`` is observed in a real run**
(``docs/solver-learning/cardiacfoam.md``, section BB). ``consumes`` names the
native files a step reads; a file an earlier step writes (the mesh, the
``.msh``, ``0/bodyAndOrgansConductivity``) is that step's ``produces``, since
it does not exist when the case is planned and fingerprinted (C8).

**Reworked 2026-09-26 (review 54b fixes, rebased in for 5.4a):**
- ``gmshToFoam`` now declares ``consumes=(_TET_MESH,)``, handing the ``.msh``
  ``gmsh`` writes to the step that reads it, the way ``records/case_outputs
  .py``'s ``gmsh_to_foam_outputs`` and every other gmsh route now do
  (review 54b M2's relation test,
  ``test_every_gmsh_route_hands_its_mesh_file_from_gmsh_to_gmsh_to_foam``).
  ``gmsh_to_foam_outputs("myocardium", "bath")`` replaces the record's own
  copy of the zone-file list, confirmed against the template's own
  ``Physical Volume("myocardium")``/``("bath")`` (BB2);
- the mesh-writer constants (``POLY_MESH_OUTPUTS``, ``ELECTRO_PROPERTIES``,
  ``WITH_DEFAULT_VALUES``) are the shared ones from ``case_outputs.py``
  (review 54b M6), not a local copy;
- ``variant_constraints={"tet": {"dimension": TET_DIMENSIONS}}`` restores
  the refusal a tet route needs (review 54b I3): bath's own native
  ``dimension`` is ``"1D"``, so a tet study that omitted ``dimension``
  would otherwise run the 1D manufactured solution on the 3D gmsh box
  silently -- the exact gap the original report's Concern 1 named. The tet
  route already carried no ``-setnumber lc`` default (review 54b M1 applied
  to bath from the start).
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

_TET_TEMPLATE = "setup/studies/tetConvergence/three_domain_box.geo.template"
_TET_MESH = "three_domain_box.msh"

AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, ("bidomainSolverCoeffs",)),
    ),
    hex_number_cells_axis("numberCells", expected_blocks=3),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

RECORD = TutorialRecord(
    name="manufacturedBathBidomain",
    native_case_relpath="manufacturedSolutions/bathBidomain",
    axes=AXES,
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            default_arguments=(
                DefaultArgument(key=MESH_DICT_KEY, values=("system/blockMeshDict.1D",)),
            ),
            consumes=BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            # BB1: the cellZones file and the four sets topoSetDict names.
            step_id="topoSet", command=("topoSet",),
            consumes=("system/topoSetDict",),
            produces=(
                "constant/polyMesh/cellZones",
                "constant/polyMesh/sets/bath",
                "constant/polyMesh/sets/bathCells",
                "constant/polyMesh/sets/myocardium",
                "constant/polyMesh/sets/myocardiumCells",
            ),
        ),
        WorkflowStep(
            step_id="gmsh",
            command=("gmsh", "-3", _TET_TEMPLATE, "-o", _TET_MESH, "-format", "msh2"),
            consumes=(_TET_TEMPLATE,),
            produces=(_TET_MESH,),
        ),
        WorkflowStep(
            # BB2: the template's two Physical Volumes become two cellZones
            # and two cellSets beside the five mesh files.
            step_id="gmshToFoam", command=("gmshToFoam", _TET_MESH),
            consumes=(_TET_MESH,),
            produces=gmsh_to_foam_outputs("myocardium", "bath"),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
        WorkflowStep(
            # BB1/BB2: the one field it writes, and the `0/` it creates to
            # hold it (the native case has no `0/`); staging would otherwise
            # carry both (plan §4, C11).
            step_id="setConductivity", command=("setTorsoOrganConductivityField",),
            consumes=("system/setTorsoOrganConductivityFieldDict",),
            produces=("0", "0/bodyAndOrgansConductivity"),
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES,
            ),
            # BB1/BB2: `electroModel::end`'s dictionary, and the verifier's
            # `<dim>_<N>_cells.dat`, whose N the verifier derives from the
            # resolved mesh (`3D_17_cells.dat` at tet lc=0.1).
            produces=(WITH_DEFAULT_VALUES, "postProcessing/*_cells.dat"),
        ),
        WorkflowStep(
            step_id="interfaceMetrics",
            command=("bathBidomainInterfaceMetrics", "-latestTime"),
            produces=("postProcessing/bathBidomainInterfaceMetrics.csv",),
        ),
    ),
    workflow_variants={
        "hex": ("mesh", "topoSet", "setConductivity", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "setConductivity", "solve", "interfaceMetrics"),
    },
    variant_selector="mesh",
    default_variant="hex",
    variant_constraints={"tet": {"dimension": TET_DIMENSIONS}},
)
