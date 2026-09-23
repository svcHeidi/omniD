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
#     monodomain_and_eikonal_1d_cable_cv_convergence
#
# Description
#     Defines configuration template for 1D cable CV convergence sweeps.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping, Sequence
from functools import partial
from itertools import product
from pathlib import Path

from omnidriver.cardiacfoam.tutorials.defaults import cable_1d_cv_convergence as defaults
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.cardiacfoam.overrides import (
    PLUGIN_ID,
    apply_electro_property_overrides,
    apply_physics_property_overrides,
    commit_case_overrides,
    merge_assignments,
    resolve_entry_overrides,
)
from omnidriver.core.specs.common import (
    resolve_run_script_path,
    resolve_spec_paths,
)
from omnidriver.core.specs.utils import load_python_module
from omnidriver.openfoam.utils import (
    plan_block_mesh_resolution,
    plan_delta_t,
    plan_end_time,
    replace_block_mesh_resolutions,
    set_delta_t,
    set_end_time,
)
from omnidriver.openfoam.mesh_provisioning import cell_counts_from_dx



def _build_cases(
    ionic_models: Sequence[str],
    ionic_model_tissue_map: Mapping[str, Sequence[str]],
    dt_values: Sequence[float],
    dx_values: Sequence[float],
    solvers: Sequence[str],
    conductivity_values: Sequence[str],
) -> list[CaseConfig]:
    cases: list[CaseConfig] = []
    for conductivity_index, conductivity in enumerate(conductivity_values, start=1):
        for ionic_model in ionic_models:
            tissues = ionic_model_tissue_map.get(ionic_model)
            if not tissues:
                raise KeyError(f"Missing tissue mapping for ionic model '{ionic_model}'")
            for tissue, dt, dx, solver in product(tissues, dt_values, dx_values, solvers):
                case_id = (
                    f"{solver}_{ionic_model}_{tissue}_DT{dt:g}_DX{dx:g}_COND{conductivity_index:02d}"
                )
                cases.append(
                    CaseConfig(
                        case_id=case_id,
                        params={
                            "ionicModel": ionic_model,
                            "tissue": tissue,
                            "dt_ms": float(dt),
                            "dx_mm": float(dx),
                            "solver": solver,
                            "conductivity": conductivity,
                            "conductivity_id": conductivity_index,
                        },
                    )
                )
    return cases


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    control_dict_relpath: Path = defaults.CONTROL_DICT_RELPATH,
    block_mesh_dict_relpath: Path = defaults.BLOCK_MESH_DICT_RELPATH,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = Path("constant/physicsProperties"),
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    cable_length_mm: float = defaults.CABLE_LENGTH_MM,
    cross_section_cell_counts: Sequence[int] = defaults.CROSS_SECTION_CELL_COUNTS,
    end_time_s: float = defaults.END_TIME_S,
) -> None:
    control_dict = case_root / control_dict_relpath
    block_mesh_dict = case_root / block_mesh_dict_relpath
    electro_properties = case_root / electro_properties_relpath
    physics_properties = case_root / physics_properties_relpath

    (x_cells,) = cell_counts_from_dx(float(case.params["dx_mm"]), (cable_length_mm,))
    cell_counts_str = f"{x_cells} {int(cross_section_cell_counts[0])} {int(cross_section_cell_counts[1])}"
    replace_block_mesh_resolutions(block_mesh_dict, cell_counts_str)
    set_delta_t(control_dict, float(case.params["dt_ms"]) * 1.0e-3)
    set_end_time(control_dict, end_time_s)

    case_overrides = {
        f"{electro_properties_scope}.conductivity": str(case.params["conductivity"]),
    }
    if electro_properties_scope != "eikonalSolverCoeffs":
        case_overrides[f"{electro_properties_scope}.tissue"] = str(case.params["tissue"])
        case_overrides[f"{electro_properties_scope}.ionicModel"] = str(case.params["ionicModel"])
        case_overrides[f"{electro_properties_scope}.solutionAlgorithm"] = str(case.params["solver"])

    apply_electro_property_overrides(electro_properties, case_overrides)
    apply_electro_property_overrides(electro_properties, electro_property_overrides)
    apply_physics_property_overrides(physics_properties, physics_property_overrides)


def _plan_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    control_dict_relpath: Path = defaults.CONTROL_DICT_RELPATH,
    block_mesh_dict_relpath: Path = defaults.BLOCK_MESH_DICT_RELPATH,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = Path("constant/physicsProperties"),
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    cable_length_mm: float = defaults.CABLE_LENGTH_MM,
    cross_section_cell_counts: Sequence[int] = defaults.CROSS_SECTION_CELL_COUNTS,
    end_time_s: float = defaults.END_TIME_S,
):
    """`TutorialSpec.plan_case` (Phase 3 Task 6). Same arithmetic as
    `_apply_case`; the block-mesh rewrite, the `deltaT`/`endTime` edits and
    the electro/physics overrides are described once and committed together
    through `commit_case_overrides`, instead of four direct writers.

    `plan_delta_t`/`plan_end_time` address `system/controlDict` by a fixed
    name (Task 3's own finding), not by `control_dict_relpath` -- this
    tutorial's own default (`defaults.shared.CONTROL_DICT_RELPATH`) already
    is `"system/controlDict"`, so this holds for every real caller; a
    caller overriding `control_dict_relpath` to something else would
    already diverge between the two control-dict-touching calls today
    (`set_delta_t`/`set_end_time` follow the override, `plan_delta_t`/
    `plan_end_time` cannot) -- an existing constraint of Task 3's design,
    not a new one this tutorial introduces.
    """
    electro_properties = case_root / electro_properties_relpath
    physics_properties = case_root / physics_properties_relpath

    (x_cells,) = cell_counts_from_dx(float(case.params["dx_mm"]), (cable_length_mm,))
    cell_counts_str = f"{x_cells} {int(cross_section_cell_counts[0])} {int(cross_section_cell_counts[1])}"
    block_mesh_document = str(block_mesh_dict_relpath)
    block_mesh_target = plan_block_mesh_resolution(block_mesh_document, cell_counts_str)

    case_overrides = {
        f"{electro_properties_scope}.conductivity": str(case.params["conductivity"]),
    }
    if electro_properties_scope != "eikonalSolverCoeffs":
        case_overrides[f"{electro_properties_scope}.tissue"] = str(case.params["tissue"])
        case_overrides[f"{electro_properties_scope}.ionicModel"] = str(case.params["ionicModel"])
        case_overrides[f"{electro_properties_scope}.solutionAlgorithm"] = str(case.params["solver"])

    electro_document = str(electro_properties_relpath)
    physics_document = str(physics_properties_relpath)
    parameters = merge_assignments(
        (plan_delta_t(float(case.params["dt_ms"]) * 1.0e-3, owner=PLUGIN_ID),),
        (plan_end_time(end_time_s, owner=PLUGIN_ID),),
        resolve_entry_overrides(
            electro_properties, case_overrides, document=electro_document,
            electro_properties_path=electro_properties,
        ),
        resolve_entry_overrides(
            electro_properties, electro_property_overrides, document=electro_document,
            electro_properties_path=electro_properties,
        ),
        resolve_entry_overrides(
            physics_properties, physics_property_overrides, document=physics_document,
        ),
    )

    return commit_case_overrides(
        case_root,
        parameters=parameters,
        extra_targets=(block_mesh_target,),
        extra_effects=(f"rewrite hex blocks in {block_mesh_document}",),
        workflow="cable_1d_cv_convergence",
        requested_by="cardiacfoam.tutorials.cable_1d_cv_convergence",
    )


def make_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = defaults.CASE_DIR_NAME,
    setup_dir_name: str | None = defaults.SETUP_DIR_NAME,
    output_dir_name: str | None = defaults.DEFAULT_OUTPUT_DIR_NAME,
    ionic_models: Sequence[str] = defaults.IONIC_MODELS,
    ionic_model_tissue_map: Mapping[str, Sequence[str]] = defaults.IONIC_MODEL_TISSUE_MAP,
    dt_values: Sequence[float] = defaults.DT_VALUES,
    dx_values: Sequence[float] = defaults.DX_VALUES,
    solvers: Sequence[str] = defaults.SOLVERS,
    conductivity_values: Sequence[str] = defaults.CONDUCTIVITY_VALUES,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    cable_length_mm: float = defaults.CABLE_LENGTH_MM,
    cross_section_cell_counts: Sequence[int] = defaults.CROSS_SECTION_CELL_COUNTS,
    end_time_s: float = defaults.END_TIME_S,
    control_dict_relpath: str | Path = defaults.CONTROL_DICT_RELPATH,
    block_mesh_dict_relpath: str | Path = defaults.BLOCK_MESH_DICT_RELPATH,
    electro_properties_relpath: str | Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: str | Path = "constant/physicsProperties",
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    run_script_relpath: str | Path = defaults.RUN_SCRIPT_RELPATH,
    parallel: bool = defaults.PARALLEL,
    postprocess_strict_artifacts: bool = False,
) -> TutorialSpec:
    ionic_models_list = [str(item) for item in ionic_models]
    dt_values_list = [float(item) for item in dt_values]
    dx_values_list = [float(item) for item in dx_values]
    solvers_list = [str(item) for item in solvers]
    conductivity_values_list = [str(item) for item in conductivity_values]

    control_dict_path = Path(control_dict_relpath)
    block_mesh_dict_path = Path(block_mesh_dict_relpath)
    electro_properties_path = Path(electro_properties_relpath)
    physics_properties_path = Path(physics_properties_relpath)
    run_script_path = Path(run_script_relpath)

    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=defaults.DEFAULT_OUTPUT_DIR_NAME,
    )

    return TutorialSpec(
        name=defaults.TUTORIAL_NAME,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=partial(
            _build_cases,
            ionic_models=ionic_models_list,
            ionic_model_tissue_map=ionic_model_tissue_map,
            dt_values=dt_values_list,
            dx_values=dx_values_list,
            solvers=solvers_list,
            conductivity_values=conductivity_values_list,
        ),
        apply_case=partial(
            _apply_case,
            electro_properties_scope=electro_properties_scope,
            control_dict_relpath=control_dict_path,
            block_mesh_dict_relpath=block_mesh_dict_path,
            electro_properties_relpath=electro_properties_path,
            physics_properties_relpath=physics_properties_path,
            electro_property_overrides=electro_property_overrides,
            physics_property_overrides=physics_property_overrides,
            cable_length_mm=cable_length_mm,
            cross_section_cell_counts=cross_section_cell_counts,
            end_time_s=end_time_s,
        ),
        plan_case=partial(
            _plan_case,
            electro_properties_scope=electro_properties_scope,
            control_dict_relpath=control_dict_path,
            block_mesh_dict_relpath=block_mesh_dict_path,
            electro_properties_relpath=electro_properties_path,
            physics_properties_relpath=physics_properties_path,
            electro_property_overrides=electro_property_overrides,
            physics_property_overrides=physics_property_overrides,
            cable_length_mm=cable_length_mm,
            cross_section_cell_counts=cross_section_cell_counts,
            end_time_s=end_time_s,
        ),
        metadata={
            "python": sys.executable,
            "expected_artifacts": [],
            "notes": "1D cable conduction-velocity convergence sweep.",
            "workflow_dag": {
                "steps": [
                    {
                        "id": "run",
                        "command": "Allrun",
                        "args": ["parallel"] if parallel else [],
                        "depends_on": []
                    },
                ]
            },
            "dx_values": dx_values_list,
            "dt_values": dt_values_list,
            "conductivity_values": conductivity_values_list,
            "ionic_models": ionic_models_list,
            "solvers": solvers_list,
            "parallel": parallel,
            "output_dir_name": output_dir.name,
            "run_script_relpath": str(run_script_path),
            "postprocess_strict_artifacts": postprocess_strict_artifacts,
        },
    )
