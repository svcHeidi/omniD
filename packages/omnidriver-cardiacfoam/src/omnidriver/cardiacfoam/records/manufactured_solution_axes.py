"""Axes shared by the multi-dimension manufactured-solution tutorials
(bath bidomain, bidomain, eikonalECG, pseudo-ECG -- tutorials-are-pointers
plan §5c: "Build them once, in a shared `records/` module ... Each record
instantiates them with its own `<solver>Coeffs` scope and file set. That is
reuse, not a second copy.").

Built for ``manufacturedBidomain`` (5.4b-B), the first of these four to
migrate; a later record imports the same three builders rather than copying
them. Nothing here is bidomain-specific: every parameter that differs
between tutorials (the document, the ``<solver>Coeffs`` scope, the workflow
step ids) is a builder argument, the same shape
``omnidriver.openfoam.axes.block_mesh_resolution.block_mesh_resolution_axis``
and this package's own ``ionic_model_axis``/``s1_s2_protocol_axis`` already
use.

**Evidence for the conventions below** (real runs against a clean
``manufacturedSolutions/bidomain`` worktree copy, logged in full in
``docs/solver-learning/cardiacfoam.md`` under "manufacturedBidomain"):

- ``system/blockMeshDict.<dim>`` (``dim`` one of ``1D``/``2D``/``3D``) is
  the native naming convention every one of these four cases uses; there is
  no plain ``system/blockMeshDict`` (owner, plan §5g Q2/Q3).
- the tet route's gmsh templates now carry
  ``DefineConstant[ lc = { <default>, Name "lc" } ]`` (owner, plan §5g Q8);
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

#: The native naming convention all four multi-dimension manufactured cases
#: share: one ``blockMeshDict`` per dimension, never a plain
#: ``system/blockMeshDict`` (owner, plan §5g Q2/Q3).
DIMENSIONS: tuple[str, ...] = ("1D", "2D", "3D")


def _block_mesh_dict_document(dimension: str) -> str:
    return f"system/blockMeshDict.{dimension}"


def dimension_axis(
    name: str, *, document: str, scope: tuple[str, ...], mesh_step_id: str = "mesh",
) -> AxisContract:
    """Build a named axis mapping a study's dimension choice (``"1D"``,
    ``"2D"`` or ``"3D"``) to ``<scope>.dimension`` plus the mesh step's
    ``-dict system/blockMeshDict.<dim>`` (a :class:`.DefaultArgument`
    replacement, owner Q3/Q7).

    ``document`` is the case-relative electroProperties-shaped document the
    ``<solver>Coeffs`` ``scope`` lives in (bidomain's own
    ``constant/electroProperties``/``("bidomainSolverCoeffs",)``).
    ``$ELECTRO_MODEL_COEFFS.dimension`` is already catalogued (enum
    ``1D``/``2D``/``3D``, ``applicable_when`` naming every manufactured ionic
    model), so this axis derives no catalog fact of its own -- it only turns
    the study value into the patch and the mesh step's argument.

    The axis declares ``value_kind="word"`` (a bare string) -- checked by
    ``tutorial_records.resolve_case_patches`` before ``resolve`` ever runs.
    Refuses by name a value that is not one of :data:`DIMENSIONS`: the mesh
    step's default-argument key is ``("-dict",)``, and a nonsense dimension
    would otherwise only surface later as blockMesh failing to find a file
    named after it.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in DIMENSIONS:
            raise ValueError(
                f"dimension axis {name!r}: {value!r} is not one of {DIMENSIONS}"
            )
        # Written pre-quoted (`'"1D"'`, literal quote characters), matching
        # the native case's own `dimension "3D";` and the old factory
        # code's identical `f'"{dimension}"'` -- proven necessary against a
        # real staged case: foamlib's own tokenizer refuses a bare `1D`/`3D`
        # ("invalid string: '1D'"), since unquoted it looks like a
        # malformed number, not a word.
        patch = AxisPatch(
            document=document, key_path=scope + ("dimension",),
            value=f'"{value}"', value_kind="word",
        )
        return AxisResult(
            patches=(patch,),
            command_arguments={mesh_step_id: ("-dict", _block_mesh_dict_document(value))},
        )

    return AxisContract(name=name, value_kind="word", resolve=resolve)


def _keep_ones_fixed(n: int, current: tuple[int, int, int]) -> tuple[int, int, int]:
    """Owner decision (d), design doc's step 4a: a direction whose CURRENT
    cell count is 1 stays 1; every other direction becomes ``n``.

    Reused across every hex ``numberCells`` axis this module builds: none of
    these tutorials' ``blockMeshDict.<dim>`` files invent their own rule for
    which directions a resolution study actually refines -- each file's own
    ``hex (`` line already says so (bidomain's own ``.1D`` is ``(1280 1 1)``,
    ``.2D`` is ``(640 640 1)``, ``.3D`` is ``(20 20 20)`` -- refining x only,
    x and y, or all three, respectively; real ``blockMesh`` runs against all
    three confirm this reads back unchanged).
    """
    return tuple(n if c != 1 else 1 for c in current)  # type: ignore[return-value]


def hex_number_cells_axis(
    name: str, *, documents: tuple[str, ...] = tuple(
        _block_mesh_dict_document(dimension) for dimension in DIMENSIONS
    ),
    expected_blocks: int = 1,
) -> AxisContract:
    """A named ``numberCells`` axis over every ``blockMeshDict.<dim>``
    document at once (P2's multi-document ``block_mesh_resolution_axis``),
    using :func:`_keep_ones_fixed` -- one study value (``N``) patches all
    three dimension files identically, regardless of which one the
    ``dimension`` axis actually selects for a given case (the same
    pattern bath's own ``numberCells`` axis uses, plan §5b T2).

    ``expected_blocks`` defaults to 1: every one of bidomain's three
    ``blockMeshDict.<dim>`` files is a single ``hex (`` block (unlike bath's
    three-domain-block files), confirmed by real ``blockMesh`` runs.
    """
    return block_mesh_resolution_axis(
        name, documents=documents, resolution=_keep_ones_fixed,
        expected_blocks=expected_blocks, value_kind="integer",
    )


def tet_number_cells_axis(name: str, *, gmsh_step_id: str = "gmsh") -> AxisContract:
    """A named ``tetNumberCells`` axis: ``N`` becomes the gmsh tet step's
    ``-setnumber lc <1/N>`` (a :class:`.DefaultArgument` replacement, owner
    Q3/Q7/Q8), and writes no document patch at all -- unlike the hex
    ``numberCells`` axis above, there is no ``blockMeshDict`` for a tet case
    to leave unwritten (the design's own reasoning for a separate axis:
    "so that a tet case writes nothing into the unused blockMeshDicts, and
    parity with the old tet route holds").

    This axis never touches ``setup/studies/tetConvergence/box.geo.template``
    itself: the template's own ``DefineConstant`` default (``lc = 0.1``,
    owner Q8's coarsest level) is what a case gets when this axis is not
    named at all, matching the module docstring's "default the record
    declares, never the values that may replace it" rule.

    Refuses by name a value that is not a positive integer -- ``1/N`` would
    otherwise be a ``ZeroDivisionError`` (``N=0``) or a nonsensical negative
    length for a study typo, surfacing at gmsh's own command line instead of
    naming this axis.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(
                f"tet-number-cells axis {name!r}: N must be a positive "
                f"integer, got {value!r}"
            )
        lc = 1.0 / value
        return AxisResult(
            patches=(),
            command_arguments={gmsh_step_id: ("-setnumber", "lc", str(lc))},
        )

    return AxisContract(name=name, value_kind="integer", resolve=resolve)
