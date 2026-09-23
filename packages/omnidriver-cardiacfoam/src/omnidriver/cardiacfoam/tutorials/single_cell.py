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
#     single_cell
#
# Description
#     Defines configuration template for single-cell scenarios.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path

from omnidriver.cardiacfoam.tutorials.defaults import single_cell as defaults
from omnidriver.cardiacfoam.overrides import (
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
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec


def _build_cases(
    ionic_models: Sequence[str],
    ionic_model_tissue_map: Mapping[str, Sequence[str]],
) -> list[CaseConfig]:
    cases: list[CaseConfig] = []
    for ionic_model in ionic_models:
        tissues = ionic_model_tissue_map.get(ionic_model)
        if not tissues:
            raise KeyError(f"Missing tissue list for ionic model '{ionic_model}'")
        for tissue in tissues:
            case_id = f"{ionic_model}_{tissue}"
            cases.append(
                CaseConfig(
                    case_id=case_id,
                    params={"ionicModel": ionic_model, "tissue": tissue},
                )
            )
    return cases


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    stimulus_map: Mapping[str, float],
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = Path("constant/physicsProperties"),
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> None:
    tissue = case.params["tissue"]
    ionic_model = case.params["ionicModel"]

    if ionic_model not in stimulus_map:
        raise KeyError(f"Missing stimulus amplitude for ionic model '{ionic_model}'")

    electro_properties_file = case_root / electro_properties_relpath
    physics_properties_file = case_root / physics_properties_relpath
    case_overrides = {
        f"{electro_properties_scope}.tissue": tissue,
        f"{electro_properties_scope}.ionicModel": ionic_model,
        f"{electro_properties_scope}.singleCellStimulus.stim_amplitude": stimulus_map[ionic_model],
    }

    apply_electro_property_overrides(electro_properties_file, case_overrides)
    apply_electro_property_overrides(electro_properties_file, electro_property_overrides)
    apply_physics_property_overrides(physics_properties_file, physics_property_overrides)


def _plan_case(
    case_root: Path,
    case: CaseConfig,
    *,
    stimulus_map: Mapping[str, float],
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    electro_properties_relpath: Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: Path = Path("constant/physicsProperties"),
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
):
    """`TutorialSpec.plan_case` (Phase 3 Task 6, single_cell as the
    template). Same effect as `_apply_case` above -- same arithmetic, same
    two override sets folded onto `constant/electroProperties` the same
    "second call wins" way -- but the actual write happens once, through
    `commit_case_overrides` (`overrides.py`), not through two direct
    `apply_electro_property_overrides` calls. Returns the committed
    `CaseWriteRecord`, or `None` when there was nothing to write.
    """
    tissue = case.params["tissue"]
    ionic_model = case.params["ionicModel"]

    if ionic_model not in stimulus_map:
        raise KeyError(f"Missing stimulus amplitude for ionic model '{ionic_model}'")

    electro_properties_file = case_root / electro_properties_relpath
    physics_properties_file = case_root / physics_properties_relpath
    case_overrides = {
        f"{electro_properties_scope}.tissue": tissue,
        f"{electro_properties_scope}.ionicModel": ionic_model,
        f"{electro_properties_scope}.singleCellStimulus.stim_amplitude": stimulus_map[ionic_model],
    }

    electro_document = str(electro_properties_relpath)
    physics_document = str(physics_properties_relpath)

    # `case_overrides` first, `electro_property_overrides` second -- the
    # same order `_apply_case` applies them in, so a key both sets name
    # resolves to the caller-supplied override, matching that function's
    # "second write wins" behaviour exactly (merge_assignments's own
    # docstring).
    electro_parameters = merge_assignments(
        resolve_entry_overrides(
            electro_properties_file, case_overrides, document=electro_document,
            electro_properties_path=electro_properties_file,
        ),
        resolve_entry_overrides(
            electro_properties_file, electro_property_overrides, document=electro_document,
            electro_properties_path=electro_properties_file,
        ),
    )
    physics_parameters = resolve_entry_overrides(
        physics_properties_file, physics_property_overrides, document=physics_document,
    )

    return commit_case_overrides(
        case_root,
        parameters=merge_assignments(electro_parameters, physics_parameters),
        workflow="single_cell",
        requested_by="cardiacfoam.tutorials.single_cell",
    )


def make_spec(
    *,
    cases_root: Path | None = None,
    case_dir_name: str = defaults.CASE_DIR_NAME,
    setup_dir_name: str | None = defaults.SETUP_DIR_NAME,
    output_dir_name: str | None = None,
    ionic_models: Sequence[str] = defaults.IONIC_MODELS,
    ionic_model_tissue_map: Mapping[str, Sequence[str]] = defaults.IONIC_MODEL_TISSUE_MAP,
    ionic_model: str | None = None,
    tissue: str | None = None,
    stimulus_map: Mapping[str, float] = defaults.STIMULUS_MAP,
    electro_properties_scope: str = defaults.ELECTRO_PROPERTIES_SCOPE,
    electro_properties_relpath: str | Path = defaults.ELECTRO_PROPERTIES_RELPATH,
    physics_properties_relpath: str | Path = "constant/physicsProperties",
    electro_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    physics_property_overrides: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    run_script_relpath: str | Path = defaults.RUN_SCRIPT_RELPATH,
    output_glob: str = defaults.OUTPUT_GLOB,
    postprocess_strict_artifacts: bool = False,
) -> TutorialSpec:
    if (ionic_model is None) != (tissue is None):
        raise ValueError(
            "ionic_model and tissue must be given together (a single-case "
            "override, for entry-mode sweeps that need build_cases() to "
            "collapse to exactly one case) or not at all (the default "
            "full-catalog ionic_models/ionic_model_tissue_map sweep)"
        )
    if ionic_model is not None:
        ionic_models = [ionic_model]
        ionic_model_tissue_map = {ionic_model: [tissue]}

    ionic_models_list = [str(item) for item in ionic_models]
    if not ionic_models_list:
        raise ValueError("ionic_models cannot be empty")

    for ionic_model in ionic_models_list:
        tissues = ionic_model_tissue_map.get(ionic_model)
        if not tissues:
            raise KeyError(f"Missing tissue mapping for ionic model '{ionic_model}'")
        if ionic_model not in stimulus_map:
            raise KeyError(f"Missing stimulus amplitude for ionic model '{ionic_model}'")

    electro_properties_path = Path(electro_properties_relpath)
    physics_properties_path = Path(physics_properties_relpath)
    run_script_path = Path(run_script_relpath)

    default_output_dir_name = defaults.OUTPUT_DIR_NAME
    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=default_output_dir_name,
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
        ),
        apply_case=partial(
            _apply_case,
            stimulus_map=stimulus_map,
            electro_properties_scope=electro_properties_scope,
            electro_properties_relpath=electro_properties_path,
            physics_properties_relpath=physics_properties_path,
            electro_property_overrides=electro_property_overrides,
            physics_property_overrides=physics_property_overrides,
        ),
        plan_case=partial(
            _plan_case,
            stimulus_map=stimulus_map,
            electro_properties_scope=electro_properties_scope,
            electro_properties_relpath=electro_properties_path,
            physics_properties_relpath=physics_properties_path,
            electro_property_overrides=electro_property_overrides,
            physics_property_overrides=physics_property_overrides,
        ),
        metadata={
            "python": sys.executable,
            "notes": "Single-cell sweep on ionic model and tissue types.",
            "workflow_dag": {
                "steps": [
                    # The selected single-cell tutorial's authored Allrun
                    # creates its one-cell mesh before launching the solver.
                    # This is an OpenFOAM execution convention declared by
                    # the cardiac tutorial, not a Core sequencing rule.
                    {"id": "mesh", "command": "blockMesh", "depends_on": []},
                    {"id": "solve", "command": "cardiacFoam", "depends_on": ["mesh"]},
                ]
            },
            "ionic_models": ionic_models_list,
            "electro_properties_relpath": str(electro_properties_path),
            "physics_properties_relpath": str(physics_properties_path),
            "electro_properties_scope": electro_properties_scope,
            "run_script_relpath": str(run_script_path),
            "output_glob": output_glob,
            "has_electro_property_overrides": bool(electro_property_overrides),
            "has_physics_property_overrides": bool(physics_property_overrides),
            "postprocess_strict_artifacts": postprocess_strict_artifacts,
        },
    )
