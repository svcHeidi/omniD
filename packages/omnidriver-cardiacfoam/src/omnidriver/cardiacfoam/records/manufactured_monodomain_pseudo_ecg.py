"""``manufacturedMonodomainPseudoECG``, the monodomain manufactured-solution record with pseudo-ECG output.
Native case: ``manufacturedSolutions/monodomainPseudoECG``; hex and tet routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult, TutorialRecord, TutorialRecordError

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, allrun_time_controls, dimension_axis, number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, redistribute_restart_state_step, solve_step

#: The `monodomainSolverCoeffs` scope, and the pseudo-ECG verifier's nested
#: echo of the tissue dimension, which the `dimension` axis keeps in step.
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)
_ECG_VERIFICATION_MODEL = ("ecgDomains", "ECG", "verificationModel")

_TET_TEMPLATE = "box.geo.template"
_TET_MESH = "box.msh"

#: ``Allrun`` meshes the hex box with ``blockMesh -dict system/blockMeshDict.<dim>D``, 3D by default.
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"
#: The N ``Allrun`` meshes at when given no ``-N``, hex and tet alike.
_ALLRUN_N = 20

#: The time step the native Allrun takes at N = 10; it scales it with the cell size squared.
_ALLRUN_STEP_AT_TEN = 0.00892857

#: ``Allrun -field``: each manufactured field's conductivity (S/m), tissue verifier and pseudo-ECG reference.
_CONDUCTIVITY_DIMENSIONS = [-1, -3, 3, 0, 0, 2, 0]
_FIELDS: dict[str, tuple[list[float], str, bool]] = {
    "anisotropic": (
        [0.106875, -0.0084931, -0.022561, 0.116682, -0.0130256, 0.0398782],
        "manufacturedAnisotropicMonodomainVerifier", True,
    ),
    "fda": ([0.111453302, 0, 0, 0.121585420, 0, 0.030396355], "manufacturedFDAMonodomainVerifier", False),
}


def field_axis(name: str) -> AxisContract:
    """``Allrun -field``: the conductivity, the tissue verifier and the pseudo-ECG reference of one manufactured field.
    The anisotropic field is 3D only; a plan at another dimension is refused by the case rules, as the Allrun refuses."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        if value not in _FIELDS:
            raise TutorialRecordError(f"field axis {name!r}: {value!r} is not one of {sorted(_FIELDS)}", code="axis_rule")
        tensor, verifier, anisotropic = _FIELDS[value]
        return AxisResult(patches=(
            AxisPatch(
                document=ELECTRO_PROPERTIES, key_path=_MONODOMAIN_SOLVER_COEFFS + ("conductivity",),
                value={"value": tensor, "dimensions": _CONDUCTIVITY_DIMENSIONS}, value_kind="dimensioned_tensor",
            ),
            AxisPatch(
                document=ELECTRO_PROPERTIES, key_path=_MONODOMAIN_SOLVER_COEFFS + ("verificationModel", "type"),
                value=verifier, value_kind="enum",
            ),
            AxisPatch(
                document=ELECTRO_PROPERTIES,
                key_path=_MONODOMAIN_SOLVER_COEFFS + _ECG_VERIFICATION_MODEL + ("anisotropic",),
                value=anisotropic, value_kind="boolean",
            ),
        ))

    return AxisContract(
        name=name, value_kind="enum", unit=None, resolve=resolve,
        description=(
            f"The manufactured field, one of {sorted(_FIELDS)} (Allrun -field): its conductivity, the tissue "
            "verifier and the pseudo-ECG's anisotropic switch. anisotropic is the rotated sin^2 field, 3D only; fda "
            "is the FDA cosine field with the diagonal conductivity."
        ),
    )


AXES = (
    field_axis("field"),
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, _MONODOMAIN_SOLVER_COEFFS),
        ecg_verification_scope=_ECG_VERIFICATION_MODEL,
        ecg_domains=(ELECTRO_PROPERTIES, _MONODOMAIN_SOLVER_COEFFS + ("ecgDomains",)),
    ),
    number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: The pseudo-ECG verifier's myocardium domain calls `electroModel::end()`, so
#: the solve writes `.withDefaultValues`. The ECG files are written in 3D only
#: (the `dimension` axis removes the ECG below it), so the predictor names them
#: from the resolved case rather than the step.
_SOLVE_OUTPUTS = (WITH_DEFAULT_VALUES, "postProcessing/*_cells.dat")

RECORD = TutorialRecord(
    name="manufacturedMonodomainPseudoECG",
    native_case_relpath="manufacturedSolutions/monodomainPseudoECG",
    axes=AXES,
    derivations=(allrun_time_controls(_ALLRUN_STEP_AT_TEN),),
    workflow_steps=(
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict=_MESH_DICT_DEFAULT,
        ),
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "internal", allrun_n=_ALLRUN_N),
        solve_step(_SOLVE_OUTPUTS),
        redistribute_restart_state_step(),
    ),
    workflow_variants={
        "hex": ("mesh", "checkMesh", "solve", "redistributeRestartState"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve", "redistributeRestartState"),
    },
    variant_selector="mesh",
    default_variant="hex",
)
