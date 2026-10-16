"""The axes every multi-dimension manufactured-solution record shares (bath bidomain, bidomain, eikonalECG, pseudo-ECG).
Each record instantiates them with its own ``<solver>Coeffs`` scope and file set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult, TutorialRecordError

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
    ecg_domains: tuple[str, tuple[str, ...]] | None = None,
) -> AxisContract:
    """A named axis mapping a dimension (one of :data:`DIMENSIONS`) to the
    mesh step's ``-dict system/blockMeshDict.<dim>`` (replacing the step's
    default argument), and, when ``solver_coefficients`` is a ``(document,
    scope)`` pair, to ``<scope>.dimension`` in that document too.

    ``ecg_verification_scope`` (pseudo-ECG) adds a second patch in the same
    document, at ``scope + ecg_verification_scope + ("dimension",)``: the
    verifier's dimension echoes the tissue dimension, and one study value
    drives both so they cannot desync. Requires ``solver_coefficients``.

    ``ecg_domains`` is the ``(document, key path)`` of the case's ECG domains,
    which run in 3D only: a 1D or 2D value removes them, as the native
    ``Allrun``'s ``#remove ecgDomains`` does.

    Refuses by name a value that is not one of :data:`DIMENSIONS`: a
    nonsense dimension would otherwise surface only as blockMesh failing to
    find a file named after it.
    """
    if ecg_verification_scope is not None and solver_coefficients is None:
        raise ValueError("ecg_verification_scope requires solver_coefficients")

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in DIMENSIONS:
            raise TutorialRecordError(f"dimension axis {name!r}: {value!r} is not one of {DIMENSIONS}")
        patches: tuple[AxisPatch, ...] = ()
        if solver_coefficients is not None:
            document, scope = solver_coefficients
            # Pre-quoted, matching the native `dimension "3D";` (module docstring).
            patches = (AxisPatch(
                document=document, key_path=scope + ("dimension",),
                value=f'"{value}"', value_kind="word",
            ),)
            if ecg_verification_scope is not None and value == "3D":
                patches += (AxisPatch(
                    document=document,
                    key_path=scope + ecg_verification_scope + ("dimension",),
                    value=f'"{value}"', value_kind="word",
                ),)
        if ecg_domains is not None and value != "3D":
            document, key_path = ecg_domains
            patches += (AxisPatch(document=document, key_path=key_path, value=None, value_kind="mapping", removes=True),)
        return AxisResult(
            patches=patches,
            command_arguments={mesh_step_id: MESH_DICT_KEY + (block_mesh_dict_document(value),)},
        )

    return AxisContract(
        name=name, value_kind="enum", unit=None, resolve=resolve,
        description=(
            f"The dimension, one of {list(DIMENSIONS)}: the mesh step reads system/blockMeshDict.<dimension> (-dict)"
            + (", and the solver's own dimension key is set to it." if solver_coefficients is not None else ".")
            + (" The ECG domains run in 3D only: 1D and 2D remove them." if ecg_domains is not None else "")
        ),
    )


#: The controlDict the derived time step is written to, and the end time it is derived from.
CONTROL_DICT_DOCUMENT = "system/controlDict"
_END_TIME_SLOT = f"{CONTROL_DICT_DOCUMENT}::endTime"


def allrun_time_step(n: int, end_time: float, step_at_ten: float) -> float:
    """The native ``Allrun``'s time step when it is given no ``-dt``: ``endTime/ceil(endTime/h)``, with
    ``h = step_at_ten*(10/N)^2``, so the step scales with the cell size squared and ends exactly at ``endTime``."""
    h = step_at_ten * (10 / n) ** 2
    steps = int(end_time / h)
    if steps * h < end_time:
        steps += 1
    return end_time / steps


def _derived_time_step(name: str, n: int, staged_case_root: Path, step_at_ten: float) -> AxisPatch:
    from foamlib import FoamFile

    try:
        end_time = FoamFile(Path(staged_case_root) / CONTROL_DICT_DOCUMENT).get("endTime")
    except (OSError, ValueError):
        end_time = None
    if isinstance(end_time, bool) or not isinstance(end_time, (int, float)) or end_time <= 0:
        raise TutorialRecordError(f"axis {name!r}: the staged {CONTROL_DICT_DOCUMENT} has no positive endTime to derive deltaT from")
    return AxisPatch(
        document=CONTROL_DICT_DOCUMENT, key_path=("deltaT",), value=allrun_time_step(n, end_time, step_at_ten),
        value_kind="scalar", yields=True, derived_from=(_END_TIME_SLOT,),
    )


def _time_step_description(step_at_ten: float | None) -> str:
    if step_at_ten is None:
        return ""
    return (
        f" Unless the study sets system/controlDict deltaT, deltaT is the native Allrun's: "
        f"endTime/ceil(endTime/({step_at_ten:g}*(10/N)^2)), from the case's endTime (a study that sets endTime sets deltaT too)."
    )


def number_cells_axis(
    name: str, *, documents: tuple[str, ...] = BLOCK_MESH_DICT_DOCUMENTS, step_at_ten: float | None,
) -> AxisContract:
    """A named ``numberCells`` axis, the native ``Allrun -N``: ``N`` patches the top-level ``N`` of each of
    ``documents``, whose blocks count ``$N`` cells along each direction that is not one cell, so it holds whichever
    file the ``dimension`` axis selects. ``step_at_ten`` is the time step the ``Allrun`` takes at ``N = 10``, from
    which it derives the step for any ``N`` (:func:`allrun_time_step`); ``None`` for a steady case, whose
    ``Allrun`` derives none."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        patches = tuple(
            AxisPatch(document=document, key_path=("N",), value=value, value_kind="integer") for document in documents
        )
        if step_at_ten is not None:
            patches += (_derived_time_step(name, value, staged_case_root, step_at_ten),)
        return AxisResult(patches=patches)

    return AxisContract(
        name=name, value_kind="integer", unit=None, exclusive_minimum=0, resolve=resolve,
        description=(
            "Cells N per unit length: the top-level N of every " + ", ".join(documents) + "."
            + _time_step_description(step_at_ten)
        ),
    )


def tet_number_cells_axis(name: str, *, gmsh_step_id: str = "gmsh", step_at_ten: float | None) -> AxisContract:
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
    negative length surfacing at gmsh's command line. ``step_at_ten`` derives
    ``deltaT`` from ``N`` as :func:`number_cells_axis` does, since the native
    ``Allrun -mesh tet -N`` does too.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        return AxisResult(
            patches=() if step_at_ten is None else (_derived_time_step(name, value, staged_case_root, step_at_ten),),
            command_arguments={gmsh_step_id: GMSH_LC_KEY + (str(1.0 / value),)},
        )

    return AxisContract(
        name=name, value_kind="integer", unit=None, exclusive_minimum=0, resolve=resolve,
        description=(
            "Cells N along the unit cube's edge for the tet route: the gmsh step gets -setnumber lc 1/N; "
            "unset, the template's own default applies." + _time_step_description(step_at_ten)
        ),
    )
