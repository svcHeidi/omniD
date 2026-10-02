"""``manufacturedBathBidomain``. Native case:
``manufacturedSolutions/bathBidomain``, the FDA bidomain-with-bath
manufactured solution (see that case's ``README.md`` for the physics).

The native ``Allrun`` runs serially (parallel is the OpenFOAM layer's
concern)::

    DIM=${1:-1D}
    runApplication blockMesh -dict system/blockMeshDict.${DIM}
    runApplication topoSet
    runApplication setTorsoOrganConductivityField
    runApplication cardiacFoam

Its ``regression/regressionTest.sh`` runs that ``Allrun`` on
``system/blockMeshDict.1D``, matching the case's own ``dimension "1D"``, so
the ``hex`` route is those four steps with ``-dict system/blockMeshDict.1D``
as the mesh step's default, replaced by the ``dimension`` axis. Each
``blockMeshDict.<dim>`` file has three ``hex (`` blocks (left bath,
myocardium, right bath), so ``numberCells`` is built with
``expected_blocks=3``.

The tet route has no native ``Allrun``; it is the route the case's tet
studies run (``setup/studies/tetConvergence/three_domain_box.geo.template``):
``gmsh``, then ``gmshToFoam``, ``checkMesh``,
``setTorsoOrganConductivityField``, the solve, and
``bathBidomainInterfaceMetrics -latestTime``. No ``topoSet``: the template's
``Physical Volume("myocardium")``/``("bath")`` already become the two
cellZones. The gmsh step carries no ``-setnumber lc`` default: gmsh uses the
template's own ``DefineConstant`` default instead.

What a study states directly, not through an axis:

- the FDA boundary variant. ``electrodePair`` is the native state. A
  ``groundElectrode`` study sets ``verificationModel.fdaBathVariant`` and
  replaces ``bathPotentialDomain.groundPatches``/``surfaceCurrentPatches`` as
  whole dictionaries, since the case writer replaces a sub-dictionary rather
  than merging into it (observed on the real file, logged as BB4 in
  ``docs/solver-learning/cardiacfoam.md``). The C++
  (``extracellularPotentialDomain.C``) is fatal on a patch listed in both;
- ``phiERefPoint`` is the native case's ``(-0.9 0.05 0.05)``; a study that
  needs another states it. It works serially at every hex resolution these
  records run.

Every step's ``produces``/``consumes`` is observed in a real run
(``docs/solver-learning/cardiacfoam.md``, section BB). ``consumes`` names the
native files a step reads; a file an earlier step writes (the mesh, the
``.msh``, ``0/bodyAndOrgansConductivity``) is that step's ``produces``, since
it does not exist when the case is planned and fingerprinted.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

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
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict="system/blockMeshDict.1D",
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
        # BB2: the template's two Physical Volumes become two cellZones and
        # two cellSets beside the five mesh files.
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "myocardium", "bath"),
        WorkflowStep(
            # BB1/BB2: the one field it writes, and the `0/` it creates to
            # hold it (the native case has no `0/`).
            step_id="setConductivity", command=("setTorsoOrganConductivityField",),
            consumes=("system/setTorsoOrganConductivityFieldDict",),
            produces=("0", "0/bodyAndOrgansConductivity"),
        ),
        # BB1/BB2: `electroModel::end`'s dictionary, and the verifier's
        # `<dim>_<N>_cells.dat`, whose N the verifier derives from the
        # resolved mesh (`3D_17_cells.dat` at tet lc=0.1).
        solve_step((WITH_DEFAULT_VALUES, "postProcessing/*_cells.dat")),
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
)
