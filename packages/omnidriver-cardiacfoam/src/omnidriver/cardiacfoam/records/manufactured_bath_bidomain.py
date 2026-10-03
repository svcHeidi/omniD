"""``manufacturedBathBidomain``, the FDA bidomain-with-bath manufactured-solution record.
Native case: ``manufacturedSolutions/bathBidomain``; hex and tet routes."""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

_TET_TEMPLATE = "setup/studies/tetConvergence/three_domain_box.geo.template"
_TET_MESH = "three_domain_box.msh"

# Each `blockMeshDict.<dim>` has three hex blocks (left bath, myocardium, right
# bath). A study sets `groundElectrode` patch dictionaries whole: the case
# writer replaces a sub-dictionary rather than merging into it.
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
        # A file an earlier step writes is that step's `produces`, not a
        # `consumes`: it does not exist when the case is planned.
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict="system/blockMeshDict.1D",
        ),
        WorkflowStep(
            # The cellZones file and the four sets topoSetDict names.
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
        # The template's two Physical Volumes become two cellZones and two
        # cellSets beside the five mesh files, so there is no topoSet step.
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "myocardium", "bath"),
        WorkflowStep(
            # The one field it writes, and the `0/` it creates to hold it
            # (the native case has no `0/`).
            step_id="setConductivity", command=("setTorsoOrganConductivityField",),
            consumes=("system/setTorsoOrganConductivityFieldDict",),
            produces=("0", "0/bodyAndOrgansConductivity"),
        ),
        # `electroModel::end`'s dictionary, and the verifier's
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
