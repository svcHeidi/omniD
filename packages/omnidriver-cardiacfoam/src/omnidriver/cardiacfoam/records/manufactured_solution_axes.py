"""The axes every multi-dimension manufactured-solution record shares (bath
bidomain, bidomain, eikonalECG, pseudo-ECG -- tutorials-are-pointers plan
§5c: "Build them once, in a shared `records/` module ... Each record
instantiates them with its own `<solver>Coeffs` scope and file set. That is
reuse, not a second copy.").

Each builder takes what differs between records as an argument (the axis
name, a workflow step id, the optional ``<solver>Coeffs`` document and
scope), the same shape
``omnidriver.openfoam.axes.block_mesh_resolution_axis`` and this package's
``ionic_model_axis``/``s1_s2_protocol_axis`` use. A record puts the axes it
builds on its own ``TutorialRecord.axes``, so ``dimension`` can mean one
thing for bidomain and another for eikonalECG.

**Merged 2026-09-26 (record-scoped axes).** ``manufacturedBidomain`` wrote
this module, and ``manufacturedEikonalECG`` then wrote
``mesh_dict_dimension_axis.py`` and ``tet_characteristic_length_axis.py``
for the same jobs; both are deleted, and both records build from here. The
two dimension builders differed in three ways, settled as follows:

- the ``<solver>Coeffs.dimension`` patch is optional (``solver_coefficients``),
  since eikonalECG's ``eikonalSolverCoeffs`` has no ``dimension`` key;
- the patch value is pre-quoted (``'"1D"'``), bidomain's form, proven
  against a real staged case: foamlib refuses a bare ``1D`` ("invalid
  string: '1D'"). eikonalECG's builder wrote it bare, but no record used
  that branch;
- the axis's ``value_kind`` is ``"enum"`` (eikonalECG's), since the axis
  accepts exactly :data:`DIMENSIONS`. bidomain's said ``"word"``.
  ``validate_value_shape`` checks both kinds identically, so this changes
  what ``describe`` reports for bidomain's ``dimension``, not any value
  accepted or refused.

**Evidence for the conventions below** (real runs, logged in
``docs/solver-learning/cardiacfoam.md`` under "manufacturedBidomain", and
G1-G9 and section E for eikonalECG):

- ``system/blockMeshDict.<dim>`` (``dim`` one of ``1D``/``2D``/``3D``) is
  the naming convention all four cases use; none has a plain
  ``system/blockMeshDict`` (owner, plan §5g Q2/Q3);
- the tet route's gmsh templates carry ``DefineConstant[ lc = { <default>,
  Name "lc" } ]`` (owner, plan §5g Q8; native commit ``60805b27``);
  ``gmsh -3 <template> -o <mesh>.msh -format msh2 -setnumber lc <v>`` runs
  correctly with ``-setnumber`` trailing every other flag (a real run at
  ``lc=0.2`` then ``lc=0.3`` produced two different meshes, 1203 and 706
  elements).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult
from omnidriver.openfoam.axes import block_mesh_resolution_axis

#: One ``blockMeshDict`` per dimension, never a plain ``system/blockMeshDict``
#: (owner, plan §5g Q2/Q3).
DIMENSIONS: tuple[str, ...] = ("1D", "2D", "3D")


def block_mesh_dict_document(dimension: str) -> str:
    return f"system/blockMeshDict.{dimension}"


BLOCK_MESH_DICT_DOCUMENTS: tuple[str, ...] = tuple(
    block_mesh_dict_document(dimension) for dimension in DIMENSIONS
)

#: The mesh step's argument the dimension axis replaces: a record declares
#: its native default under this key (``DefaultArgument``, owner Q3/Q7).
MESH_DICT_KEY: tuple[str, ...] = ("-dict",)

#: The gmsh step's argument the tet axis replaces, likewise.
GMSH_LC_KEY: tuple[str, ...] = ("-setnumber", "lc")

#: The only dimension a tet route's gmsh template builds: every
#: ``box.geo.template`` is the unit cube ``Box(1) = {0, 0, 0, 1, 1, 1}``,
#: meshed with ``gmsh -3``. A record's tet routes admit their ``dimension``
#: axis only at this value, or unset (``TutorialRecord.variant_constraints``).
#: This restores the refusal the old pseudo-ECG and eikonalECG ``make_spec``
#: raised, ``mesh_family='tet' requires dimensions=['3D'] ... (the unit-cube
#: tet mesh has no 1D/2D variant)``, which the records had lost (review 54b
#: I3, 2026-09-26): ``dimension`` picks the blockMesh dictionary, which a tet
#: route never runs.
TET_DIMENSIONS: tuple[str, ...] = ("3D",)


def dimension_axis(
    name: str, *, mesh_step_id: str = "mesh",
    solver_coefficients: tuple[str, tuple[str, ...]] | None = None,
) -> AxisContract:
    """A named axis mapping a dimension (one of :data:`DIMENSIONS`) to the
    mesh step's ``-dict system/blockMeshDict.<dim>`` (replacing the step's
    default argument), and, when ``solver_coefficients`` is a ``(document,
    scope)`` pair, to ``<scope>.dimension`` in that document too.

    ``$ELECTRO_MODEL_COEFFS.dimension`` is already catalogued (enum
    ``1D``/``2D``/``3D``), so this axis derives no catalog fact of its own.

    Refuses by name a value that is not one of :data:`DIMENSIONS`: a
    nonsense dimension would otherwise surface only as blockMesh failing to
    find a file named after it.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in DIMENSIONS:
            raise ValueError(f"dimension axis {name!r}: {value!r} is not one of {DIMENSIONS}")
        patches: tuple[AxisPatch, ...] = ()
        if solver_coefficients is not None:
            document, scope = solver_coefficients
            # Pre-quoted, matching the native `dimension "3D";` (module docstring).
            patches = (AxisPatch(
                document=document, key_path=scope + ("dimension",),
                value=f'"{value}"', value_kind="word",
            ),)
        return AxisResult(
            patches=patches,
            command_arguments={mesh_step_id: MESH_DICT_KEY + (block_mesh_dict_document(value),)},
        )

    return AxisContract(name=name, value_kind="enum", resolve=resolve)


def _keep_ones_fixed(
    n: int, current: tuple[int, int, int],
    extents: tuple[float, float, float] | None = None,
) -> tuple[int, int, int]:
    """Owner decision (d), design doc's step 4a: a direction whose CURRENT
    cell count is 1 stays 1; every other direction becomes ``n``.

    Each ``blockMeshDict.<dim>``'s own ``hex (`` line already says which
    directions a resolution study refines (bidomain's ``.1D`` is
    ``(1280 1 1)``, ``.2D`` is ``(640 640 1)``, ``.3D`` is ``(20 20 20)``),
    so no per-dimension table restates it. This is also the rule the
    deleted ``BLOCK_MESH_RESOLUTION_BY_DIMENSION`` table encoded for
    eikonalECG (``N=10`` on ``.1D`` gives ``(10 1 1)``, on ``.2D``
    ``(10 10 1)``).

    Corrected 2026-09-26 (5.4b-N landing): takes the ``extents`` argument
    ``block_mesh_resolution_axis`` now passes every resolution; this rule
    counts cells, so it ignores it.
    """
    del extents
    return tuple(n if c != 1 else 1 for c in current)  # type: ignore[return-value]


def hex_number_cells_axis(name: str, *, expected_blocks: int = 1) -> AxisContract:
    """A named ``numberCells`` axis over every ``blockMeshDict.<dim>`` at
    once, using :func:`_keep_ones_fixed`: one study value ``N`` patches all
    three dimension files, whichever one the ``dimension`` axis selects
    (plan §5b T2).

    ``expected_blocks`` defaults to 1: bidomain's and eikonalECG's
    ``blockMeshDict.<dim>`` files are each a single ``hex (`` block,
    confirmed by real ``blockMesh`` runs (bath's have three).
    """
    return block_mesh_resolution_axis(
        name, documents=BLOCK_MESH_DICT_DOCUMENTS, resolution=_keep_ones_fixed,
        expected_blocks=expected_blocks, value_kind="integer",
    )


def tet_number_cells_axis(name: str, *, gmsh_step_id: str = "gmsh") -> AxisContract:
    """A named ``tetNumberCells`` axis: ``N`` becomes the gmsh step's
    ``-setnumber lc <1/N>`` (replacing the step's default argument), and no
    document patch -- a tet case writes nothing into the unused
    ``blockMeshDict``s (the design's reason for a separate axis).

    ``lc = 1/N``, not a study-supplied ``lc``: every native
    ``.geo.template`` parameterises resolution by a cell count ``N`` along
    the unit cube's edge (the hex route's vocabulary), and G5/G8's real-gmsh
    evidence confirms ``-setnumber lc <v>`` overrides the template's
    ``DefineConstant`` default at any value. With the axis unnamed, a case
    gets the template's own default.

    Refuses by name a value that is not a positive integer (``bool``
    excluded): ``1/N`` would otherwise be a ``ZeroDivisionError`` or a
    negative length surfacing at gmsh's command line.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"tet-number-cells axis {name!r}: N must be a positive integer, got {value!r}"
            )
        return AxisResult(command_arguments={gmsh_step_id: GMSH_LC_KEY + (str(1.0 / value),)})

    return AxisContract(name=name, value_kind="integer", resolve=resolve)
