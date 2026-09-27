"""``niederer2011``, the Niederer et al. (2011) N-version slab benchmark
(design doc ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
design.md``; plan ``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-
remaining.md`` §5c "5.4b-N", §5d, and the owner's Q12 decision).

Replaces ``cardiacfoam.tutorials.niederer_2011``/``tutorials.defaults
.niederer_2011`` (deleted alongside this record; the module's ``__all__``
listed exactly the values this record either derives directly from the
native case or drops because the native case already holds them -- see the
per-write table below). Native case: ``NiedererEtAl2011verification``
(moved there from ``NiedererEtAl2011/NiedererEtAl2011verification`` by
native ``7a04349b``).

**Every write the old ``_plan_case``/``_apply_case`` made, accounted for**
(plan §1's own instruction, "identify every write... and account for each
one: an axis, a direct study key, or dropped"):

| old write | now |
|---|---|
| ``monodomainSolverCoeffs.tissue`` | direct study key (a study names it, e.g. ``constant/electroProperties:monodomainSolverCoeffs.tissue``) |
| ``monodomainSolverCoeffs.ionicModel`` | direct study key -- this record allows no ``ionicModel`` axis: the case fixes ``TNNPcompactBatched`` with ``batchedIntegrator rushLarsen`` (native ``0489be3c``, owner 2026-09-26; it was ``TNNP`` with ``solver RKF45``), and a study wanting another names the key directly |
| ``monodomainSolverCoeffs.solutionAlgorithm`` | direct study key |
| ``system/blockMeshDict`` hex block rewrite | ``dx`` axis (hex route) |
| tet ``slab.geo`` ``__LC__`` substitution | ``tetDx`` axis (tet route; native ``60805b27`` already turned the template's own substitution into a real ``DefineConstant``, so this axis need not render a file at all -- it only passes ``-setnumber lc <v>`` to the ``gmsh`` step) |
| ``system/controlDict:deltaT`` | direct study key (``dt_values`` in ms -> ``system/controlDict:deltaT`` in seconds; no unit-converting axis exists or is needed -- a study states the converted value itself) |
| ``system/controlDict:endTime`` | direct study key, one explicit value per case (the old ``end_time_by_dx`` lookup table is gone: a zip study lists ``dx``/``deltaT``/``endTime`` together, so nothing derives one from another) |
| ``electro_property_overrides``/``physics_property_overrides`` | direct study keys, same as before -- these were always ``None`` by default (no write at all), so nothing here migrates them either |

**No ``SLAB_SIZE_MM`` table.** The old module carried the slab's physical
size (20 x 3 x 7 mm) as a public, overridable ``make_spec`` default
parameter -- a second, independently-editable copy of a fact
``system/blockMeshDict`` already states in its own ``vertices``/``scale``.
This record does not restate it either, as a Python constant or otherwise:
the ``dx`` axis's own ``resolution`` callable reads the document's real
extent every time it runs, via ``block_mesh_resolution_axis``'s own
``extents`` argument (**corrected 2026-09-26, controller review of
`2125168`**: an earlier version of this record cited a private
``_SLAB_EXTENT_M`` constant here, because the axis builder did not yet
expose the staged document's extent to ``resolution`` at all -- fixed at
the source, in ``axes/block_mesh_resolution.py`` itself, rather than
worked around here with a constant needing its own drift test).

**Workflow steps, taken from the native ``Allrun``**::

    runApplication blockMesh
    runApplication cardiacFoam
    runApplication -o postProcess -func Niedererpoints -latestTime
    runApplication -o postProcess -func Niedererlines -latestTime

(the ``parallel`` branch -- ``decomposePar``/``runParallel
cardiacFoam``/``reconstructPar`` -- is owner Q6: serial only, parallel is
the OpenFOAM layer's job through its own ``parallel_execution``, not a
record concern). The tet route has no native ``Allrun`` of its own (owner
Q2/Q7/Q8): it is declared here, citing
``setup/studies/tetConvergence/slab.geo.template`` and its own study
(``sweep_tet_generic.json``), with no native ``Allrun`` change.

**The probe files are declared on the step a real run shows writes each one
LAST, as required by topic B Task 7** (plan §5c, item 2). A real run
(logged in ``docs/solver-learning/cardiacfoam.md``, section N) confirmed:
the ``solve`` step's ``cardiacFoam`` writes ``postProcessing/Niedererpoints/
<writeTime>/activationTime`` at every write time (the function object's own
``writeControl writeTime``), but the LAST write -- the one staging actually
sees, since A5 excludes every step's own ``produces`` from the NEXT
staging -- is the following ``postProcess -func Niedererpoints -latestTime``
step's own re-evaluation, which writes exactly one directory,
``postProcessing/Niedererpoints/0/activationTime`` (not
``.../0.015/...``: ``-latestTime`` restarts its own instance numbering at
the case's ``startTime``, "0", regardless of what time it actually
evaluates). So the probe paths are declared on ``samplePoints``/
``sampleLines``, each as the FIRST (and only) entry of that step's own
``produces`` -- **plain paths, no format**: declaring one now would fail
C12, since no ``artifact_value_reader`` exists yet (that is topic B Task
7's own job, not this record's).

Artifact ids (``record_execution.record_artifact_id``), for Task 7:
``record.samplePoints.0`` is ``postProcessing/Niedererpoints/0/
activationTime``; ``record.sampleLines.0`` is ``postProcessing/
Niedererlines/0/activationTime``.

**Corrected 2026-09-26 (topic B Task 7):** ``samplePoints``' path now
declares ``ACTIVATION_PROBES_FORMAT``, whose reader
(``activation_probes.ActivationProbeReader``) exists, so C12 holds.
``sampleLines`` stays a plain path: nothing reads it as a quantity yet.

**Corrected 2026-09-27 (Q9, owner decision: sample the exact point).** The
above used to add ``writeCellCentres`` and ``samplePointCentres`` steps
after ``samplePoints``, probing the containing cell's centre through the
same cell search, because the native ``system/Niedererpoints`` set no
``interpolationScheme`` (OpenFOAM's ``cell`` default). Both steps are
removed: the reader now requires ``interpolationScheme cellPoint``, read
from the case's own dict, and reports the probe's own configured location,
so no second probe of cell centres is needed. The native dict itself is a
separate, owner-authorised change, not yet committed (the probe-cellpoint
report says why); until it lands, this record's ``samplePoints`` output
reads as ``cell`` and the reader refuses it by name.

**``constant/electroProperties.withDefaultValues``** (owner Q13, corrected
by P4's R4): declared on the ``solve`` step, because a real run of this
case's solver (``monodomainSolver``, via ``electroModel::end()``) writes
it -- confirmed by the same real run logged in section N, not assumed from
``restitutionCurves``'s own (negative) finding.
"""

from __future__ import annotations

from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisResult, ProducedPath, TutorialRecord, WorkflowStep,
)
from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.mesh_provisioning import cell_counts_from_dx

from ..activation_probes import ACTIVATION_PROBES_FORMAT
from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import GMSH_LC_KEY

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
    itself (``block_mesh_resolution_axis``'s ``extents`` argument, added
    2026-09-26: see ``axes/block_mesh_resolution.py``'s own dated
    correction). Never a Python constant restating that geometry: a
    different slab (a different ``vertices``/``scale``) gives different
    counts for the same ``dx``, because this reads the file every time.

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
    """The tet route's own axis: adds ``-setnumber lc <dx>`` to the
    ``gmsh`` step (owner Q2/Q8; ``docs/solver-learning/cardiacfoam.md`` G5,
    "``-setnumber lc v`` overrides ``DefineConstant[ lc = … ]``"). Produces
    no ``AxisPatch`` at all -- ``slab.geo.template`` needs no rendering any
    more (native ``60805b27``), only this one command-line argument. With
    the axis unnamed, gmsh uses the template's own ``DefineConstant``
    default.

    Not ``manufactured_solution_axes.tet_number_cells_axis``: that axis
    takes a cell count ``N`` on the unit cube and passes ``lc = 1/N``; this
    slab is not a unit cube, and its study states ``lc`` itself, in metres.
    The key is the shared ``GMSH_LC_KEY`` (review 54b M6, 2026-09-26: this
    restated ``("-setnumber", "lc")``).
    """

    def resolve(value: Any, staged_case_root) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        dx = float(value)
        if dx <= 0:
            raise ValueError(f"tet-dx axis {name!r}: dx must be positive, got {value!r}")
        return AxisResult(command_arguments={"gmsh": GMSH_LC_KEY + (str(dx),)})

    return AxisContract(name=name, value_kind="scalar", resolve=resolve)


#: This record's own axes (``TutorialRecord.axes``, record-scoped since
#: 2026-09-26).
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
#: tet study's coarsest rung). Corrected 2026-09-26 (review 54b M1): a
#: `_DEFAULT_LC_M = "0.0005"` default argument restated that value, and its
#: comment cited `sweep_tet_generic.json`'s `dx_values`, a key the 5.4b-N
#: study rewrite had deleted.

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
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            consumes=(_BLOCK_MESH_DICT_DOCUMENT,),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="gmsh",
            command=("gmsh", "-3", _TET_GEO_TEMPLATE_RELPATH, "-o", _TET_MSH_RELPATH, "-format", "msh2"),
            consumes=(_TET_GEO_TEMPLATE_RELPATH,),
            produces=(_TET_MSH_RELPATH,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", _TET_MSH_RELPATH),
            consumes=(_TET_MSH_RELPATH,),
            # Review 54b M2: the full real-run set (this declared only the
            # hex route's six, "matching restitutionCurves's precedent",
            # which has no tet route).
            produces=gmsh_to_foam_outputs("internal"),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                ELECTRO_PROPERTIES, _PHYSICS_DOCUMENT, "system/controlDict",
                "system/fvSchemes", "system/fvSolution",
                "system/Niedererpoints", "system/Niedererlines",
            ),
            produces=(WITH_DEFAULT_VALUES,),
        ),
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
