"""The axes every multi-dimension manufactured-solution record shares (bath bidomain, bidomain, eikonalECG, pseudo-ECG).
Each record instantiates them with its own ``<solver>Coeffs`` scope and file set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult
from omnidriver.openfoam.axes import block_mesh_resolution_axis

#: One ``blockMeshDict`` per dimension; none of these cases has a plain ``system/blockMeshDict``.
DIMENSIONS: tuple[str, ...] = ("1D", "2D", "3D")


def block_mesh_dict_document(dimension: str) -> str:
    return f"system/blockMeshDict.{dimension}"


BLOCK_MESH_DICT_DOCUMENTS: tuple[str, ...] = tuple(
    block_mesh_dict_document(dimension) for dimension in DIMENSIONS
)

#: The mesh step's argument the dimension axis replaces: a record declares
#: its native default under this key (``DefaultArgument``).
MESH_DICT_KEY: tuple[str, ...] = ("-dict",)

#: The gmsh argument a tet axis passes. The gmsh steps declare no default for
#: it: with no study value, gmsh uses the template's own ``DefineConstant``
#: default, and an axis that names it adds it (``WorkflowStep.argv`` appends
#: a contribution no default claims).
GMSH_LC_KEY: tuple[str, ...] = ("-setnumber", "lc")


def dimension_axis(
    name: str, *, mesh_step_id: str = "mesh",
    solver_coefficients: tuple[str, tuple[str, ...]] | None = None,
    ecg_verification_scope: tuple[str, ...] | None = None,
) -> AxisContract:
    """A named axis mapping a dimension (one of :data:`DIMENSIONS`) to the
    mesh step's ``-dict system/blockMeshDict.<dim>`` (replacing the step's
    default argument), and, when ``solver_coefficients`` is a ``(document,
    scope)`` pair, to ``<scope>.dimension`` in that document too.

    ``ecg_verification_scope`` (pseudo-ECG) adds a second patch in the same
    document, at ``scope + ecg_verification_scope + ("dimension",)``: the
    verifier's dimension echoes the tissue dimension, and one study value
    drives both so they cannot desync. Requires ``solver_coefficients``.

    Refuses by name a value that is not one of :data:`DIMENSIONS`: a
    nonsense dimension would otherwise surface only as blockMesh failing to
    find a file named after it.
    """
    if ecg_verification_scope is not None and solver_coefficients is None:
        raise ValueError("ecg_verification_scope requires solver_coefficients")

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
            if ecg_verification_scope is not None:
                patches += (AxisPatch(
                    document=document,
                    key_path=scope + ecg_verification_scope + ("dimension",),
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
    """A direction whose cell count is 1 stays 1; the others become ``n``, so no per-dimension table is needed."""
    del extents
    return tuple(n if c != 1 else 1 for c in current)  # type: ignore[return-value]


def hex_number_cells_axis(name: str, *, expected_blocks: int = 1) -> AxisContract:
    """A named ``numberCells`` axis over every ``blockMeshDict.<dim>`` at
    once, using :func:`_keep_ones_fixed`: one study value ``N`` patches all
    three dimension files, whichever one the ``dimension`` axis selects.

    ``expected_blocks`` defaults to 1: bidomain's and eikonalECG's
    ``blockMeshDict.<dim>`` files are each a single ``hex (`` block (bath's
    have three).
    """
    return block_mesh_resolution_axis(
        name, documents=BLOCK_MESH_DICT_DOCUMENTS, resolution=_keep_ones_fixed,
        expected_blocks=expected_blocks, value_kind="integer",
    )


def tet_number_cells_axis(name: str, *, gmsh_step_id: str = "gmsh") -> AxisContract:
    """A named ``tetNumberCells`` axis: ``N`` becomes the gmsh step's
    ``-setnumber lc <1/N>`` (added to the step's command line), and no
    document patch -- a tet case writes nothing into the unused
    ``blockMeshDict``s (the design's reason for a separate axis).

    ``lc = 1/N``, not a study-supplied ``lc``: every native
    ``.geo.template`` parameterises resolution by a cell count ``N`` along
    the unit cube's edge (the hex route's vocabulary). With the axis unnamed,
    a case gets the template's own default.

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
