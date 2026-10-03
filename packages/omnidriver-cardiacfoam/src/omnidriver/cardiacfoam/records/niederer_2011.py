"""``niederer2011``, the Niederer et al. (2011) N-version slab benchmark.
Native case: ``NiedererEtAl2011verification``; a hex (blockMesh) and a tet (gmsh) route."""

from __future__ import annotations

from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisResult, ProducedPath, TutorialRecord, WorkflowStep,
)
from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.case_planning import cell_counts_from_dx

from ..activation_probes import ACTIVATION_PROBES_FORMAT
from .case_outputs import WITH_DEFAULT_VALUES
from .manufactured_solution_axes import GMSH_LC_KEY
from .routes import block_mesh_step, gmsh_route, solve_step

_PHYSICS_DOCUMENT = "constant/physicsProperties"
_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict"
_TET_GEO_TEMPLATE_RELPATH = "setup/studies/tetConvergence/slab.geo.template"
_TET_MSH_RELPATH = "slab.msh"
#: The native case's `probes` function (`system/Niedererpoints`) and the file
#: it writes last. `postProcess -latestTime` numbers its own instance from the
#: case's `startTime`, so the directory is `0`, not the evaluated time. Each
#: probe path is declared on the step that writes it last, since staging
#: excludes a step's own `produces` from the next step's input.
_POINTS_FUNCTION = "Niedererpoints"
POINTS_PATH = "postProcessing/Niedererpoints/0/activationTime"

DX_AXIS_NAME = "dx"
TET_DX_AXIS_NAME = "tetDx"

MESH_SELECTOR_NAME = "mesh"
HEX_VARIANT = "hex"
TET_VARIANT = "tet"

def _hex_cell_counts_from_dx(
    dx_m: Any, current: tuple[int, int, int],
    extents: tuple[float, float, float] | None,
) -> tuple[int, int, int]:
    """``dx`` (metres) to the slab's hex cell counts, over the extent read live from ``blockMeshDict``."""
    del current
    dx = float(dx_m)
    if dx <= 0:
        raise ValueError(f"dx-axis {DX_AXIS_NAME!r}: dx must be positive, got {dx_m!r}")
    if extents is None:
        raise ValueError(
            f"dx-axis {DX_AXIS_NAME!r}: {_BLOCK_MESH_DICT_DOCUMENT!r} has no "
            "parseable vertices/scale to read a physical extent from"
        )
    return cell_counts_from_dx(dx, extents)


def _tet_dx_axis(name: str) -> AxisContract:
    """The tet route's axis: ``-setnumber lc <dx>`` on the ``gmsh`` step, in metres, with no template rendering."""

    def resolve(value: Any, staged_case_root) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        dx = float(value)
        if dx <= 0:
            raise ValueError(f"tet-dx axis {name!r}: dx must be positive, got {value!r}")
        return AxisResult(command_arguments={"gmsh": GMSH_LC_KEY + (str(dx),)})

    return AxisContract(name=name, value_kind="scalar", resolve=resolve)


#: This record's own axes (``TutorialRecord.axes``).
AXES = (
    block_mesh_resolution_axis(
        DX_AXIS_NAME,
        documents=(_BLOCK_MESH_DICT_DOCUMENT,),
        resolution=_hex_cell_counts_from_dx,
        expected_blocks=1,
        value_kind="scalar",
    ),
    _tet_dx_axis(TET_DX_AXIS_NAME),
)

#: The gmsh step passes no default `-setnumber lc`: with no `tetDx`, gmsh
#: uses `slab.geo.template`'s own `DefineConstant` default.

RECORD = TutorialRecord(
    name="niederer2011",
    native_case_relpath="NiedererEtAl2011verification",
    axes=AXES,
    variant_selector=MESH_SELECTOR_NAME,
    default_variant=HEX_VARIANT,
    workflow_variants={
        HEX_VARIANT: ("mesh", "solve", "samplePoints", "sampleLines"),
        TET_VARIANT: ("gmsh", "gmshToFoam", "checkMesh", "solve", "samplePoints", "sampleLines"),
    },
    workflow_steps=(
        block_mesh_step((_BLOCK_MESH_DICT_DOCUMENT,)),
        # The tet route has no native Allrun; it is declared from slab.geo.template.
        *gmsh_route(_TET_GEO_TEMPLATE_RELPATH, _TET_MSH_RELPATH, "internal"),
        # electroModel::end() writes electroProperties.withDefaultValues for this solver.
        solve_step((WITH_DEFAULT_VALUES,), consumes=("system/Niedererpoints", "system/Niedererlines")),
        WorkflowStep(
            step_id="samplePoints",
            command=("postProcess", "-func", _POINTS_FUNCTION, "-latestTime"),
            produces=(ProducedPath(POINTS_PATH, format=ACTIVATION_PROBES_FORMAT),),
        ),
        WorkflowStep(
            step_id="sampleLines",
            command=("postProcess", "-func", "Niedererlines", "-latestTime"),
            produces=("postProcessing/Niedererlines/0/activationTime",),
        ),
    ),
)
