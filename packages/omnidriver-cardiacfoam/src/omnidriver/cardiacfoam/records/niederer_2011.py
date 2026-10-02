"""``niederer2011``, the Niederer et al. (2011) N-version slab benchmark.
Native case: ``NiedererEtAl2011verification``.

This record does not restate the slab's physical size (20 x 3 x 7 mm) as a
Python constant: the ``dx`` axis's own ``resolution`` callable reads
``system/blockMeshDict``'s real ``vertices``/``scale`` extent every time it
runs.

Workflow steps are taken from the native ``Allrun``::

    runApplication blockMesh
    runApplication cardiacFoam
    runApplication -o postProcess -func Niedererpoints -latestTime
    runApplication -o postProcess -func Niedererlines -latestTime

(the ``parallel`` branch -- ``decomposePar``/``runParallel
cardiacFoam``/``reconstructPar`` -- is the OpenFOAM layer's job through its
own ``parallel_execution``, not a record concern). The tet route has no
native ``Allrun`` of its own: it is declared here, citing
``setup/studies/tetConvergence/slab.geo.template`` and its own study
(``sweep_tet_generic.json``), with no native ``Allrun`` change.

The probe files are declared on the step a real run shows writes each one
last. A real run (logged in ``docs/solver-learning/cardiacfoam.md``, section
N) confirmed: the ``solve`` step's ``cardiacFoam`` writes
``postProcessing/Niedererpoints/<writeTime>/activationTime`` at every write
time, but the last write -- the one staging actually sees, since each step's
own ``produces`` is excluded from the next staging -- is the following
``postProcess -func Niedererpoints -latestTime`` step's own re-evaluation,
which writes exactly one directory,
``postProcessing/Niedererpoints/0/activationTime`` (not ``.../0.015/...``:
``-latestTime`` restarts its own instance numbering at the case's
``startTime``, "0", regardless of what time it actually evaluates). So the
probe paths are declared on ``samplePoints``/``sampleLines``, each as the
first (and only) entry of that step's own ``produces``.

Artifact ids (``record_execution.record_artifact_id``): ``record.samplePoints.0``
is ``postProcessing/Niedererpoints/0/activationTime``;
``record.sampleLines.0`` is ``postProcessing/Niedererlines/0/activationTime``.

``samplePoints``' path declares ``ACTIVATION_PROBES_FORMAT``, whose reader
(``activation_probes.ActivationProbeReader``) exists, so C12 holds.
``sampleLines`` stays a plain path: nothing reads it as a quantity yet.

The native ``system/Niedererpoints`` sets ``interpolationScheme cellPoint``,
so each probe samples its own configured point.

``constant/electroProperties.withDefaultValues`` is declared on the ``solve``
step, because a real run of this case's solver (``monodomainSolver``, via
``electroModel::end()``) writes it -- confirmed by the same real run logged
in section N, not assumed from ``restitutionCurves``'s own (negative)
finding.
"""

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
#: it writes last, from `postProcess -latestTime` (section N, N2).
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
    """``dx`` (metres, isotropic cell size) -> the slab's three hex cell
    counts, via the same ``cell_counts_from_dx`` the cable tutorials share,
    over ``extents`` -- the document's own physical extent, read live from
    ``system/blockMeshDict``'s ``vertices``/``scale`` by the axis builder
    itself. Never a Python constant restating that geometry: a different
    slab (a different ``vertices``/``scale``) gives different counts for the
    same ``dx``, because this reads the file every time.

    ``current`` (this document's own resolution before this axis runs) is
    unused: unlike bath's ``groundElectrode`` axis, no direction here ever
    "stays 1" -- every one of the slab's three axes is always refined.

    ``extents`` is never ``None`` for the real case (``system/
    blockMeshDict`` always has a ``vertices`` block), so a ``None`` here
    means the staged document could not be read at all -- refused by name,
    not silently defaulted.
    """
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
    """The tet route's own axis: adds ``-setnumber lc <dx>`` to the ``gmsh``
    step (``docs/solver-learning/cardiacfoam.md`` G5, "``-setnumber lc v``
    overrides ``DefineConstant[ lc = … ]``"). Produces no ``AxisPatch`` at
    all -- ``slab.geo.template`` needs no rendering, only this one
    command-line argument. With the axis unnamed, gmsh uses the template's
    own ``DefineConstant`` default.

    Not ``manufactured_solution_axes.tet_number_cells_axis``: that axis
    takes a cell count ``N`` on the unit cube and passes ``lc = 1/N``; this
    slab is not a unit cube, and its study states ``lc`` itself, in metres.
    The key is the shared ``GMSH_LC_KEY``.
    """

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
#: uses `slab.geo.template`'s own `DefineConstant` default (0.0005 m, the
#: tet study's coarsest rung).

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
        *gmsh_route(_TET_GEO_TEMPLATE_RELPATH, _TET_MSH_RELPATH, "internal"),
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
