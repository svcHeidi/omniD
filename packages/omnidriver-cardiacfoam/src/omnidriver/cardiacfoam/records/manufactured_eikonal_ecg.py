"""``manufacturedEikonalECG``, the eikonal activation-time and template ECG manufactured-solution record.
Native case: ``manufacturedSolutions/eikonalECG``; hex, tet and the tet route with the error field."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, TutorialRecord, TutorialRecordError, WorkflowStep,
)

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

_TET_TEMPLATE_RELPATH = "box.geo.template"
_TET_MESH = "box.msh"
#: The N ``Allrun`` meshes at when given no ``-N``, hex and tet alike.
_ALLRUN_N = 20

_ECG = ("eikonalSolverCoeffs", "ecgDomains", "ECG")

#: ``Allrun -template``: what each manufactured template writes beneath the ECG domain. singleEvent is the case's own
#: sampling (-6 to 92 by 0.25), so it sets the template word alone.
_TEMPLATES: dict[str, tuple[tuple[tuple[str, ...], Any, str], ...]] = {
    "singleEvent": ((("verificationModel", "template"), "singleEvent", "enum"),),
    "sine": (
        (("sampling", "start"), 0.0, "scalar"),
        (("sampling", "end"), 2.0, "scalar"),
        (("sampling", "deltaT"), 0.01, "scalar"),
        (("verificationModel", "template"), "sine", "enum"),
    ),
}

#: ``Allrun -electrodes five`` writes ``#remove "R.*"`` into the electrode positions: only E1-E5 stay.
_FIVE_ELECTRODES_REMOVE = re.compile("R.*")
_ELECTRODES = ("five", "all")


def template_axis(name: str) -> AxisContract:
    """``Allrun -template``: the manufactured ECG template and the sampling window it is read over."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in _TEMPLATES:
            raise TutorialRecordError(f"template axis {name!r}: {value!r} is not one of {sorted(_TEMPLATES)}", code="axis_rule")
        return AxisResult(patches=tuple(
            AxisPatch(document=ELECTRO_PROPERTIES, key_path=_ECG + key_path, value=item, value_kind=kind)
            for key_path, item, kind in _TEMPLATES[value]
        ))

    return AxisContract(
        name=name, value_kind="enum", unit=None, resolve=resolve,
        description=(
            f"The manufactured ECG template, one of {sorted(_TEMPLATES)} (Allrun -template): singleEvent, the case's "
            "own, one action-potential-like event sampled from -6 to 92 by 0.25; sine, sin(2 pi s) sampled from 0 to 2 "
            "by 0.01 (the ECG domain's sampling start, end and deltaT, and verificationModel.template)."
        ),
    )


def electrodes_axis(name: str) -> AxisContract:
    """``Allrun -electrodes``: five removes every electrode the case names ``R.*``, as the Allrun's ``#remove "R.*"``
    does; all keeps the case's electrodes."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        if value not in _ELECTRODES:
            raise TutorialRecordError(f"electrodes axis {name!r}: {value!r} is not one of {list(_ELECTRODES)}", code="axis_rule")
        if value == "all":
            return AxisResult()
        from foamlib import FoamFile

        positions = FoamFile(Path(staged_case_root) / ELECTRO_PROPERTIES).get(_ECG + ("electrodePositions",))
        if not hasattr(positions, "keys"):
            raise TutorialRecordError(
                f"electrodes axis {name!r}: {ELECTRO_PROPERTIES} holds no {'.'.join(_ECG)}.electrodePositions "
                "dictionary to keep five electrodes of", code="axis_rule",
            )
        names = [str(key) for key in positions.keys() if key is not None]
        return AxisResult(patches=tuple(
            AxisPatch(
                document=ELECTRO_PROPERTIES, key_path=_ECG + ("electrodePositions", electrode),
                value=None, value_kind="vector3", removes=True,
            )
            for electrode in names if _FIVE_ELECTRODES_REMOVE.fullmatch(electrode)
        ))

    return AxisContract(
        name=name, value_kind="enum", unit=None, resolve=resolve,
        description=(
            f"The ECG electrodes, one of {list(_ELECTRODES)} (Allrun -electrodes): five keeps E1-E5 and removes every "
            "electrode named R.*; all keeps the case's 161. Unset, the case's own electrodes stay."
        ),
    )


#: The dimension axis takes no `solver_coefficients`: `eikonalSolverCoeffs` has
#: no `dimension` key (unlike bidomain's and bath's), so it sets the mesh step's
#: `-dict` argument and, in 1D and 2D, removes the 3D-only ECG.
AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh", ecg_domains=(ELECTRO_PROPERTIES, ("eikonalSolverCoeffs", "ecgDomains")),
    ),
    number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
    template_axis("template"),
    electrodes_axis("electrodes"),
)

#: `eikonalMyocardiumDomain` does not override `electroModel::end()`, so the
#: solve writes `.withDefaultValues` (unlike `singleCellSolver`). The ECG files
#: are written in 3D only (the `dimension` axis removes the ECG below it), so the
#: predictor names them from the resolved case rather than the step.
_SOLVE_OUTPUTS = (WITH_DEFAULT_VALUES, "postProcessing/manufacturedEikonalActivationTime.dat")

# The native Allrun meshes with `blockMesh -dict system/blockMeshDict.3D`.
_MESH_STEP = block_mesh_step(
    BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict="system/blockMeshDict.3D",
)
_SOLVE_STEP = solve_step(_SOLVE_OUTPUTS, consumes=("0/activationTime",))
_WRITE_CELL_CENTRES_STEP = WorkflowStep(
    step_id="writeCellCentres",
    command=("postProcess", "-func", "writeCellCentres", "-latestTime"),
    # No `produces`: its output lands in a time directory, which cannot be
    # declared (`WorkflowStep` refuses `{`/`}`, and there is no other literal
    # path for a time-varying instance), and staging drops it regardless.
)

RECORD = TutorialRecord(
    name="manufacturedEikonalECG",
    native_case_relpath="manufacturedSolutions/eikonalECG",
    axes=AXES,
    workflow_steps=(
        _MESH_STEP, _SOLVE_STEP, *gmsh_route(_TET_TEMPLATE_RELPATH, _TET_MESH, "internal", allrun_n=_ALLRUN_N),
        _WRITE_CELL_CENTRES_STEP,
    ),
    variant_selector="mesh",
    default_variant="hex",
    workflow_variants={
        "hex": ("mesh", "checkMesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
        "tet-errorLocalisation": ("gmsh", "gmshToFoam", "checkMesh", "solve", "writeCellCentres"),
    },
)
