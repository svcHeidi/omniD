#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     manufactured_monodomain_total_lagrangian_em
#
# Description
#     Defines configuration template for boundary-constrained manufactured
#     electromechanics scenarios.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from omnidriver.cardiacfoam.tutorials.defaults import manufactured_monodomain_total_lagrangian_em as defaults
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.cardiacfoam.overrides import (
    PLUGIN_ID,
    commit_case_overrides,
    merge_assignments,
    resolve_entry_overrides,
)
from omnidriver.core.specs.common import (
    resolve_run_script_path,
    resolve_spec_paths,
)
from omnidriver.openfoam.mutators import update_foam_entry
from omnidriver.openfoam.utils import (
    plan_block_mesh_resolution,
    plan_delta_t,
)
from .manufactured_monodomain_pseudo_ecg import (
    _build_cases,
    _case_output_filename,
)


def _case_output_filename(case: CaseConfig) -> str:
    dimension = str(case.params["dimension"])
    cells = int(case.params["cells"])
    solver = str(case.params["solver"])
    return f"{dimension}_{cells}_cells_{solver}.dat"


def _archive_output_dir(case_root: Path) -> Path:
    return case_root / "postProcessing"


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    control_dict_relpath: Path = defaults.CONTROL_DICT_RELPATH,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    electromechanical_properties_relpath: Path = defaults.ELECTROMECHANICAL_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = defaults.PHYSICS_PROPERTIES_RELPATH,
    block_mesh_dict_template: str = defaults.BLOCK_MESH_DICT_TEMPLATE,
    electro_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    electromechanical_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    physics_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    verification_model_type: str = defaults.ELECTROMECHANICAL_VERIFICATION_MODEL_TYPE,
) -> None:
    """`TutorialSpec.apply_case` -- thin wrapper over `_plan_case` (Phase 3
    Task 6's completion, 2026-09-23 decision, "a parameter asserts a final
    state, not only a value"). The independent direct-write implementation
    this function used to be is retired now that its byte parity with
    `_plan_case` has been proven (this tutorial's own characterization
    test) -- collapsing it earlier would have made that proof circular
    (Task 6's own report). `TutorialSpec.apply_case` still has no default
    (`core/runtime/models.py`), so every spec must still supply a callable
    here regardless; `invoke_case_mutation` never calls this one in
    production once `plan_case` is set (it prefers `plan_case`
    unconditionally), so this exists only for a caller that still invokes
    `apply_case` directly (e.g. this tutorial's own characterization test).
    """
    _plan_case(
        case_root, case,
        electro_properties_scope=electro_properties_scope,
        control_dict_relpath=control_dict_relpath,
        electro_properties_relpath=electro_properties_relpath,
        electromechanical_properties_relpath=electromechanical_properties_relpath,
        physics_properties_relpath=physics_properties_relpath,
        block_mesh_dict_template=block_mesh_dict_template,
        electro_property_overrides=electro_property_overrides,
        electromechanical_property_overrides=electromechanical_property_overrides,
        physics_property_overrides=physics_property_overrides,
        verification_model_type=verification_model_type,
    )


def _plan_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    control_dict_relpath: Path = defaults.CONTROL_DICT_RELPATH,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    electromechanical_properties_relpath: Path = defaults.ELECTROMECHANICAL_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = defaults.PHYSICS_PROPERTIES_RELPATH,
    block_mesh_dict_template: str = defaults.BLOCK_MESH_DICT_TEMPLATE,
    electro_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    electromechanical_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    physics_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    verification_model_type: str = defaults.ELECTROMECHANICAL_VERIFICATION_MODEL_TYPE,
):
    """`TutorialSpec.plan_case` (Phase 3 Task 6). Same arithmetic as
    `_apply_case`.

    **Corrected 2026-09-23:** `verification_model_type` used to be folded
    into the same `resolve_entry_overrides` batch as the `electroProperties`
    keys, under
    ``sequentialElectroMechanicalCoeffs.electromechanicalVerificationModel.type``.
    That key matches nothing the native solver reads, and the mismatch was
    two-fold, not one: (1) the leaf name is wrong --
    `electromechanicalVerificationModel.C`'s `New`/`configured` read
    `dict.subDict("verificationModel")` then `.lookup("type")`, never a
    `electromechanicalVerificationModel` sub-dict (confirmed against
    `~/noFrontendCardiacFoam_minor_errors/src/verificationModels/
    electromechanicsVerification/electromechanicalVerificationModel.C`, and
    against the tutorial's own
    `tutorials/manufacturedSolutions/monodomainTotalLagrangianEM/constant/
    electroMechanicalProperties`, which carries `verificationModel { type
    manufacturedElectromechanicsVerifier; ... }` -- no
    `electromechanicalVerificationModel` block at all); and (2) the *document*
    was wrong too -- this key lives in `electroMechanicalProperties`, which
    `dict_key_allowlist.json`'s own waiver notes explicitly own outside
    `dict_entries_catalog.py` ("belong to electroMechanicalProperties or the
    MMS verifiers, not to electroProperties"). Routing it through
    `resolve_entry_overrides`/`is_electro=False` validated it against the
    *physicsProperties* catalog (`_PHYSICS_ENTRIES_BY_PATH`, which only
    declares `type`), so the call was unconditionally doomed regardless of
    the leaf name -- fixing the typo alone would not have made it pass. Since
    no catalog in this package claims `electroMechanicalProperties`, this
    write goes through `update_foam_entry` directly, after the channel
    commit, the same "uncataloged document stays a direct write" pattern
    `manufactured_bath_bidomain`'s `grad_scheme`/`phi_tolerance` already
    establish -- not a regression to the pre-Task-2 fallback, since this
    document was never catalog-addressable to begin with.

    `electromechanical_properties` (for `electromechanical_property_overrides`,
    a caller-supplied passthrough, currently unused by any in-tree caller) is
    still addressed through `resolve_entry_overrides` with the real
    case-relative `electromechanical_properties_relpath` as its `document`;
    that call is a no-op today (nothing passes a non-`None` override) but
    would hit the identical catalog gap the moment something did -- flagged
    here rather than fixed, since fixing an unused parameter's plumbing is
    not part of this correction.
    """
    dimension = str(case.params["dimension"])
    solver = str(case.params["solver"])
    cells = int(case.params["cells"])
    dt_value = float(case.params["dt"])

    electro_properties = case_root / electro_properties_relpath
    electromechanical_properties = case_root / electromechanical_properties_relpath
    physics_properties = case_root / physics_properties_relpath
    block_mesh_dict_relpath = Path(block_mesh_dict_template.format(dimension=dimension))

    try:
        cell_counts = defaults.BLOCK_MESH_RESOLUTION_BY_DIMENSION[dimension].format(cells=cells)
    except KeyError as exc:
        raise ValueError(f"Unsupported dimension: {dimension}") from exc
    block_mesh_document = str(block_mesh_dict_relpath)
    block_mesh_target = plan_block_mesh_resolution(block_mesh_document, cell_counts)

    electro_document = str(electro_properties_relpath)
    electromechanical_document = str(electromechanical_properties_relpath)
    physics_document = str(physics_properties_relpath)

    parameters = merge_assignments(
        (plan_delta_t(dt_value, owner=PLUGIN_ID),),
        resolve_entry_overrides(
            electro_properties,
            {
                f"{electro_properties_scope}.dimension": f'"{dimension}"',
                f"{electro_properties_scope}.solutionAlgorithm": solver,
            },
            document=electro_document, electro_properties_path=electro_properties,
        ),
        resolve_entry_overrides(
            electro_properties, electro_property_overrides, document=electro_document,
            electro_properties_path=electro_properties,
        ),
        resolve_entry_overrides(
            electromechanical_properties, electromechanical_property_overrides,
            document=electromechanical_document,
        ),
        resolve_entry_overrides(
            physics_properties, physics_property_overrides, document=physics_document,
        ),
    )

    record = commit_case_overrides(
        case_root,
        parameters=parameters,
        extra_targets=(block_mesh_target,),
        extra_effects=(f"rewrite hex blocks in {block_mesh_document}",),
        workflow="manufactured_monodomain_total_lagrangian_em",
        requested_by="cardiacfoam.tutorials.manufactured_monodomain_total_lagrangian_em",
    )

    # See this function's own docstring: electroMechanicalProperties has no
    # catalog in this package, so this write is direct, not channel-routed --
    # and lands at verificationModel.type (electromechanicalVerificationModel.C's
    # actual read), not the electromechanicalVerificationModel.type this used
    # to write.
    update_foam_entry(
        electromechanical_properties, "type", verification_model_type,
        scope=["sequentialElectroMechanicalCoeffs", "verificationModel"],
    )

    return record




def make_spec(
    *,
    cases_root: Path | None = None,
    tutorial_name: str = defaults.TUTORIAL_NAME,
    case_dir_name: str = defaults.CASE_DIR_NAME,
    setup_dir_name: str | None = defaults.SETUP_DIR_NAME,
    output_dir_name: str | None = None,
    number_cells: Sequence[int] = defaults.NUMBER_CELLS,
    dt_values: Sequence[float] = defaults.DT_VALUES,
    dimensions: Sequence[str] = defaults.DIMENSIONS,
    solver_types: Sequence[str] = defaults.SOLVER_TYPES,
    piecewise_sweep: bool = defaults.PIECEWISE_SWEEP,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    control_dict_relpath: str | Path = defaults.CONTROL_DICT_RELPATH,
    electro_properties_relpath: str | Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    electromechanical_properties_relpath: str | Path = defaults.ELECTROMECHANICAL_PROPERTIES_RELPATH,
    physics_properties_relpath: str | Path = defaults.PHYSICS_PROPERTIES_RELPATH,
    block_mesh_dict_template: str = defaults.BLOCK_MESH_DICT_TEMPLATE,
    run_script_relpath: str | Path = defaults.RUN_SCRIPT_RELPATH,
    electro_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    electromechanical_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    physics_property_overrides: Sequence[dict[str, object]] | dict[str, object] | None = None,
    verification_model_type: str = defaults.ELECTROMECHANICAL_VERIFICATION_MODEL_TYPE,
    run_in_parallel: bool = defaults.RUN_IN_PARALLEL,
    postprocess_strict_artifacts: bool = False,
) -> TutorialSpec:
    dimensions_list = [str(item) for item in dimensions]
    cells_list = [int(item) for item in number_cells]
    dt_values_list = [float(item) for item in dt_values]
    solver_types_list = [str(item) for item in solver_types]
    control_dict_path = Path(control_dict_relpath)
    electro_properties_path = Path(electro_properties_relpath)
    electromechanical_properties_path = Path(electromechanical_properties_relpath)
    physics_properties_path = Path(physics_properties_relpath)
    run_script_path = Path(run_script_relpath)

    if piecewise_sweep and len(cells_list) != len(dt_values_list):
        raise ValueError(
            "piecewise_sweep requires number_cells and dt_values to have the same length"
        )

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=defaults.OUTPUT_DIR_NAME,
    )

    return TutorialSpec(
        name=tutorial_name,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=partial(
            _build_cases,
            dt_values=dt_values_list,
            number_cells=cells_list,
            dimensions=dimensions_list,
            solver_types=solver_types_list,
            piecewise_sweep=piecewise_sweep,
        ),
        apply_case=partial(
            _apply_case,
            electro_properties_scope=electro_properties_scope,
            control_dict_relpath=control_dict_path,
            electro_properties_relpath=electro_properties_path,
            electromechanical_properties_relpath=electromechanical_properties_path,
            physics_properties_relpath=physics_properties_path,
            block_mesh_dict_template=block_mesh_dict_template,
            electro_property_overrides=electro_property_overrides,
            electromechanical_property_overrides=electromechanical_property_overrides,
            physics_property_overrides=physics_property_overrides,
            verification_model_type=verification_model_type,
        ),
        plan_case=partial(
            _plan_case,
            electro_properties_scope=electro_properties_scope,
            control_dict_relpath=control_dict_path,
            electro_properties_relpath=electro_properties_path,
            electromechanical_properties_relpath=electromechanical_properties_path,
            physics_properties_relpath=physics_properties_path,
            block_mesh_dict_template=block_mesh_dict_template,
            electro_property_overrides=electro_property_overrides,
            electromechanical_property_overrides=electromechanical_property_overrides,
            physics_property_overrides=physics_property_overrides,
            verification_model_type=verification_model_type,
        ),
        metadata={
            "notes": (
                "Manufactured electromechanics MMS benchmark. "
                "Vm, D, lambda, and Ta are rigorous MMS targets."
            ),
            "workflow_dag": {
                "steps": [
                    {
                        "id": "mesh",
                        "command": "blockMesh",
                        "args": ["-dict", f"system/blockMeshDict.{dimensions_list[-1]}"],
                        "depends_on": [],
                    },
                    {"id": "solve", "command": "cardiacFoam", "depends_on": ["mesh"]},
                ]
            },
            "dimensions": dimensions_list,
            "solver_types": solver_types_list,
            "piecewise_sweep": piecewise_sweep,
            "control_dict_relpath": str(control_dict_path),
            "electro_properties_relpath": str(electro_properties_path),
            "electromechanical_properties_relpath": str(electromechanical_properties_path),
            "physics_properties_relpath": str(physics_properties_path),
            "electro_properties_scope": electro_properties_scope,
            "block_mesh_dict_template": block_mesh_dict_template,
            "run_script_relpath": str(run_script_path),
            "run_in_parallel": run_in_parallel,
            "has_electro_property_overrides": bool(electro_property_overrides),
            "has_electromechanical_property_overrides": bool(electromechanical_property_overrides),
            "has_physics_property_overrides": bool(physics_property_overrides),
            "postprocess_strict_artifacts": postprocess_strict_artifacts,
        },
    )
