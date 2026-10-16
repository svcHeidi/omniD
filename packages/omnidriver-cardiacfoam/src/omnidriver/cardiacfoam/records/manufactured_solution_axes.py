"""The axes every multi-dimension manufactured-solution record shares (bath bidomain, bidomain, eikonalECG, pseudo-ECG).
Each record instantiates them with its own ``<solver>Coeffs`` scope and file set."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult, Derivation, TutorialRecordError

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


#: The controlDict the native Allrun writes its time controls into.
CONTROL_DICT_DOCUMENT = "system/controlDict"
#: The axes that are the native ``Allrun -N``: one study names at most one N.
N_AXES: tuple[str, ...] = ("numberCells", "tetNumberCells")


def allrun_time_step(n: int, end_time: float, step_at_ten: float) -> float:
    """The native ``Allrun``'s time step when it is given no ``-dt``: ``endTime/ceil(endTime/h)``, with
    ``h = step_at_ten*(10/N)^2``, so the step scales with the cell size squared and ends exactly at ``endTime``."""
    h = step_at_ten * (10 / n) ** 2
    steps = int(end_time / h)
    if steps * h < end_time:
        steps += 1
    return end_time / steps


def _case_value(staged_case_root: Path, document: str, key: str) -> Any:
    from foamlib import FoamFile

    try:
        return FoamFile(Path(staged_case_root) / document).get(key)
    except (OSError, ValueError):
        return None


def stated_n(stated: Mapping[str, Any]) -> int | None:
    """The ``N`` a study states through :data:`N_AXES`; refused by name when it states two different ones."""
    values = {stated[name] for name in N_AXES if name in stated}
    if len(values) > 1:
        raise TutorialRecordError(f"{' and '.join(N_AXES)} are one Allrun -N; the study states {sorted(values)}")
    return next(iter(values), None)


def allrun_time_controls(step_at_ten: float, *, mesh_document: str = "system/blockMeshDict.3D") -> Derivation:
    """The time controls the native ``Allrun`` writes: ``deltaT`` from ``N`` and ``endTime``
    (:func:`allrun_time_step`, ``step_at_ten`` the step at ``N = 10``), and ``writeInterval = endTime``.

    Derived when the study states ``N`` (:data:`N_AXES`) or ``endTime``; whichever it leaves out is the case's own
    (``N`` from ``mesh_document``). A study key on ``deltaT`` or ``writeInterval`` replaces the derived one."""
    end_time_slot = f"{CONTROL_DICT_DOCUMENT}::endTime"

    def derive(stated: Mapping[str, Any], staged_case_root: Path) -> tuple[AxisPatch, ...]:
        n = stated_n(stated)
        end_time = stated.get(end_time_slot)
        if n is None and end_time is None:
            return ()
        if n is None:
            n = _case_value(staged_case_root, mesh_document, "N")
        if end_time is None:
            end_time = _case_value(staged_case_root, CONTROL_DICT_DOCUMENT, "endTime")
        for name, value in (("N", n), ("endTime", end_time)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise TutorialRecordError(f"no positive {name} to derive the Allrun's deltaT from (found {value!r})")
        patches = (AxisPatch(
            document=CONTROL_DICT_DOCUMENT, key_path=("deltaT",), value=allrun_time_step(n, end_time, step_at_ten),
            value_kind="scalar", yields=True,
        ),)
        if end_time_slot in stated:
            patches += (AxisPatch(
                document=CONTROL_DICT_DOCUMENT, key_path=("writeInterval",), value=end_time,
                value_kind="scalar", yields=True,
            ),)
        return patches

    return Derivation(
        name="allrunTimeControls", derive=derive,
        description=(
            f"When the study states N ({' or '.join(N_AXES)}) or system/controlDict endTime, deltaT is the native "
            f"Allrun's endTime/ceil(endTime/({step_at_ten:g}*(10/N)^2)), the case's own N or endTime standing in for "
            "the one not stated; a stated endTime also sets writeInterval to it. A study key on deltaT or "
            "writeInterval replaces the derived value."
        ),
    )


def number_cells_axis(name: str, *, documents: tuple[str, ...] = BLOCK_MESH_DICT_DOCUMENTS) -> AxisContract:
    """A named ``numberCells`` axis, the native ``Allrun -N``: ``N`` patches the top-level ``N`` of each of
    ``documents``, whose blocks count ``$N`` cells along each direction that is not one cell, so it holds whichever
    file the ``dimension`` axis selects. A record whose ``Allrun`` derives its time step from ``N`` declares
    :func:`allrun_time_controls` too."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        return AxisResult(patches=tuple(
            AxisPatch(document=document, key_path=("N",), value=value, value_kind="integer") for document in documents
        ))

    return AxisContract(
        name=name, value_kind="integer", unit=None, exclusive_minimum=0, resolve=resolve,
        description="Cells N per unit length: the top-level N of every " + ", ".join(documents) + ".",
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
    negative length surfacing at gmsh's command line. It is the native
    ``Allrun -mesh tet -N``, so :func:`allrun_time_controls` reads it too.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        return AxisResult(command_arguments={gmsh_step_id: GMSH_LC_KEY + (str(1.0 / value),)})

    return AxisContract(
        name=name, value_kind="integer", unit=None, exclusive_minimum=0, resolve=resolve,
        description=(
            "Cells N along the unit cube's edge for the tet route: the gmsh step gets -setnumber lc 1/N; "
            "unset, the template's own default applies."
        ),
    )
