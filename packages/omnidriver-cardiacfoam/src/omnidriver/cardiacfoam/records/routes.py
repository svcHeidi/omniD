"""The workflow steps several cardiacFOAM records share, stated once.

``scripts/check-case-writes.py`` scans this package: nothing here writes a case.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import DefaultArgument, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, gmsh_to_foam_outputs
from .manufactured_solution_axes import GMSH_LC_KEY, MESH_DICT_KEY

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


def gmsh_route(
    template: str, mesh: str, *physical_volumes: str, allrun_n: int | None = None,
) -> tuple[WorkflowStep, ...]:
    """The tet route's mesh steps: ``gmsh`` on ``template`` into ``mesh``,
    ``gmshToFoam``, ``checkMesh``. ``physical_volumes`` are the template's
    ``Physical Volume`` names (``gmsh_to_foam_outputs``). ``allrun_n`` is the
    ``N`` the case's ``Allrun -mesh tet`` meshes at when given no ``-N``: the
    gmsh step's default is then ``-setnumber lc 1/N``, which an axis naming
    ``lc`` replaces. Without it the template's own ``DefineConstant`` applies."""
    defaults = () if allrun_n is None else (DefaultArgument(key=GMSH_LC_KEY, values=(str(1.0 / allrun_n),)),)
    return (
        WorkflowStep(
            step_id="gmsh", command=("gmsh", "-3", template, "-o", mesh, "-format", "msh2"),
            default_arguments=defaults, consumes=(template,), produces=(mesh,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", mesh),
            consumes=(mesh,), produces=gmsh_to_foam_outputs(*physical_volumes),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
    )


def cable_cv_summary_step() -> WorkflowStep:
    """The cable's own ``setup/extract_cv.py``: the conduction velocity from the solve's ``activationTime`` probes,
    written as ``postProcessing/<case folder>_cv_summary.json`` (and its CSVs), which the case's ``table_summary.py``
    collects from each case of a sweep (``<output>/cases/<case id>/``)."""
    return WorkflowStep(
        step_id="cvSummary", command=("./setup/extract_cv.py",),
        default_arguments=(DefaultArgument(key=("--output-dir",), values=("postProcessing",)),),
        consumes=("setup/extract_cv.py",),
        produces=(
            "postProcessing/cv_summary.txt", "postProcessing/*_cv_summary.json",
            "postProcessing/*_activation_times.csv", "postProcessing/*_segments.csv",
        ),
    )


def redistribute_restart_state_step() -> WorkflowStep:
    """``redistributeRestartState`` after the parallel solve's ``reconstructPar``, for a record whose ``Allrun`` runs it
    in its parallel branch: the models' restart-state files, which ``reconstructPar`` leaves in the processor
    directories. A serial run leaves it out."""
    return WorkflowStep(step_id="redistributeRestartState", command=("redistributeRestartState",), parallel_only=True)
