"""The workflow steps several cardiacFOAM records share, stated once.

``scripts/check-case-writes.py`` scans this package: nothing here writes a case.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, gmsh_to_foam_outputs
from .manufactured_solution_axes import MESH_DICT_KEY

#: The documents ``cardiacFoam`` itself reads in every record.
SOLVE_DOCUMENTS: tuple[str, ...] = (
    "system/controlDict", "system/fvSchemes", "system/fvSolution",
    "constant/physicsProperties", ELECTRO_PROPERTIES,
)


def block_mesh_step(consumes: tuple[str, ...], *, default_dict: str | None = None) -> WorkflowStep:
    """``blockMesh``; ``default_dict`` is the ``-dict`` a record whose cases
    hold one ``blockMeshDict`` per dimension runs when no axis picks one."""
    default_arguments = (
        () if default_dict is None else (DefaultArgument(key=MESH_DICT_KEY, values=(default_dict,)),)
    )
    return WorkflowStep(
        step_id="mesh", command=("blockMesh",), default_arguments=default_arguments,
        consumes=consumes, produces=POLY_MESH_OUTPUTS,
    )


def solve_step(produces: tuple, *, consumes: tuple[str, ...] = ()) -> WorkflowStep:
    """``cardiacFoam``, reading :data:`SOLVE_DOCUMENTS` and ``consumes``."""
    return WorkflowStep(
        step_id="solve", command=("cardiacFoam",),
        consumes=SOLVE_DOCUMENTS + consumes, produces=produces,
    )


def gmsh_route(template: str, mesh: str, *physical_volumes: str) -> tuple[WorkflowStep, ...]:
    """The tet route's mesh steps: ``gmsh`` on ``template`` into ``mesh``,
    ``gmshToFoam``, ``checkMesh``. ``physical_volumes`` are the template's
    ``Physical Volume`` names (``gmsh_to_foam_outputs``). The gmsh step
    declares no ``-setnumber lc`` default, so the template's own
    ``DefineConstant`` applies unless an axis names it."""
    return (
        WorkflowStep(
            step_id="gmsh", command=("gmsh", "-3", template, "-o", mesh, "-format", "msh2"),
            consumes=(template,), produces=(mesh,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", mesh),
            consumes=(mesh,), produces=gmsh_to_foam_outputs(*physical_volumes),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
    )
