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
#     manufactured_monodomain_1d3d
#
# Description
#     Defines the manufactured 1D-3D coupled monodomain tutorial.
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
from itertools import product

from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.cardiacfoam.overrides import (
    PLUGIN_ID,
    commit_case_overrides,
    merge_assignments,
    resolve_entry_overrides,
)
from omnidriver.core.specs.common import (
    resolve_spec_paths,
)
from omnidriver.openfoam.case_planning import (
    plan_block_mesh_resolution,
    plan_delta_t,
    plan_end_time,
)
from omnidriver.openfoam.mutators import update_foam_entry


def _build_cases(
    graph_ids: Sequence[str],
    number_cells: Sequence[int],
    dt_values: Sequence[float],
) -> list[CaseConfig]:
    # We expect these three sequences to be zipped (same length)
    cases: list[CaseConfig] = []
    for graph_id, cells, dt in zip(graph_ids, number_cells, dt_values):
        case_id = f"{cells}"
        cases.append(
            CaseConfig(
                case_id=case_id,
                params={
                    "graph_id": str(graph_id),
                    "cells": int(cells),
                    "dt": float(dt),
                },
            )
        )
    return cases


def _apply_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_property_overrides: dict[str, object] | None = None,
    end_time: float | None = None,
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
        electro_property_overrides=electro_property_overrides,
        end_time=end_time,
    )


    # The actual execution is handled by the generic executor running the workflow_dag


def _plan_case(
    case_root: Path,
    case: CaseConfig,
    *,
    electro_property_overrides: dict[str, object] | None = None,
    end_time: float | None = None,
):
    """`TutorialSpec.plan_case` (Phase 3 Task 6). The `blockMeshDict.3D` ->
    `.active` copy convention stays a direct write -- it is not a parameter,
    it decides which document the channel will patch -- and runs first, same
    as `_apply_case`; only the `replace_block_mesh_resolutions` rewrite that
    follows it moves to the channel, addressing the `.active` copy this step
    just created. The `purkinjeGraph.<id>` -> `purkinjeGraph` copy is a
    source artifact (Task 7's classification, not this task's), left as a
    direct `shutil.copy2` exactly as `_apply_case` still does it.

    **Corrected 2026-09-24 (review of Phase 3 Task 7): both of the above stay
    direct for the same underlying reason, not two unrelated ones.** Neither
    is "a routing convention" and "a source artifact that stays direct" as
    two separate, settled shapes -- both are blocked on the same missing
    channel capability: **artifact staging**. The channel can *reference* an
    artifact (`source_artifacts`, the `source_artifact` `Precondition` kind)
    but has no primitive to *place* one's bytes at a case-relative
    destination without either patching an existing document's keys
    (`render_patch_case_files`'s ordinary targets) or authoring a whole new
    document's logical content from a caller-supplied string
    (`plan_verbatim_content`, Task 7's own addition -- deliberately not used
    here: `purkinjeGraph` is the same "large asset, not a small
    hand-editable document" class `RenderedFile`'s docstring excludes from
    embedding, so routing it through `plan_verbatim_content` would be the
    wrong fix even though it is mechanically possible for a file this
    small). The `.active` copy is a case input for exactly the same reason
    (`system/blockMeshDict.3D.active` is what the `mesh` workflow step reads,
    so this write authors a real case input, not mere bookkeeping) and hits
    the identical gap: there is a source file already in the case and a
    destination path, and no channel primitive for "stage this one to that
    one." Both are tracked in this plan as blocked on that missing
    capability, not as settled exceptions the way `write_cell_set` is.
    """
    graph_id = str(case.params["graph_id"])
    cells = int(case.params["cells"])
    dt_value = float(case.params["dt"])

    block_mesh_dict = case_root / "system" / "blockMeshDict.3D"
    block_mesh_active = case_root / "system" / "blockMeshDict.3D.active"
    block_mesh_active.write_text(block_mesh_dict.read_text())
    block_mesh_document = "system/blockMeshDict.3D.active"
    block_mesh_target = plan_block_mesh_resolution(
        block_mesh_document, f"{cells} {cells} {cells}",
    )

    source_graph = case_root / "constant" / f"purkinjeGraph.{graph_id}"
    destination_graph = case_root / "constant" / "purkinjeGraph"
    if not source_graph.exists():
        raise FileNotFoundError(f"Missing graph file: {source_graph}")
    shutil.copy2(source_graph, destination_graph)

    control_dict_parameters = [plan_delta_t(dt_value, owner=PLUGIN_ID)]
    if end_time is not None:
        control_dict_parameters.append(plan_end_time(end_time, owner=PLUGIN_ID))

    electro_properties = case_root / "constant" / "electroProperties"
    electro_parameters = resolve_entry_overrides(
        electro_properties, electro_property_overrides,
        document="constant/electroProperties", electro_properties_path=electro_properties,
    ) if electro_property_overrides else ()

    parameters = merge_assignments(control_dict_parameters, electro_parameters)

    return commit_case_overrides(
        case_root,
        parameters=parameters,
        extra_targets=(block_mesh_target,),
        extra_effects=(f"rewrite hex blocks in {block_mesh_document}",),
        workflow="manufactured_monodomain_1d3d",
        requested_by="cardiacfoam.tutorials.manufactured_monodomain_1d3d",
    )


def make_spec(
    *,
    cases_root: Path | None = None,
    tutorial_name: str = "manufacturedMonodomain1D3D",
    case_dir_name: str = "manufacturedSolutions/monodomain1D3D",
    setup_dir_name: str = "setup",
    output_dir_name: str = "setup/studies/coupledConvergence/results",
    graph_ids: Sequence[str] = ("nodes011", "nodes021", "nodes041", "nodes081"),
    number_cells: Sequence[int] = (10, 20, 40, 80),
    dt_values: Sequence[float] = (1.40174e-04 * (80/10)**2, 1.40174e-04 * (80/20)**2, 1.40174e-04 * (80/40)**2, 1.40174e-04),
    end_time: float = 0.1,
    electro_property_overrides: dict[str, object] | None = None,
    postprocess_strict_artifacts: bool = False,
) -> TutorialSpec:
    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=output_dir_name,
    )
    graph_ids_list = [str(item) for item in graph_ids]
    cells_list = [int(item) for item in number_cells]
    dt_values_list = [float(item) for item in dt_values]

    return TutorialSpec(
        name=tutorial_name,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=partial(
            _build_cases,
            graph_ids=graph_ids_list,
            number_cells=cells_list,
            dt_values=dt_values_list,
        ),
        apply_case=partial(
            _apply_case,
            electro_property_overrides=electro_property_overrides,
            end_time=end_time,
        ),
        plan_case=partial(
            _plan_case,
            electro_property_overrides=electro_property_overrides,
            end_time=end_time,
        ),
        metadata={
            "notes": "Manufactured coupled 1D-3D monodomain convergence benchmark",
            "workflow_dag": {
                "steps": [
                    {
                        "id": "mesh",
                        "command": "blockMesh",
                        "args": ["-dict", "system/blockMeshDict.3D.active"],
                        "depends_on": [],
                    },
                    {
                        "id": "solve",
                        "command": "cardiacFoam",
                        "depends_on": ["mesh"],
                    },
                ]
            },
            "postprocess_strict_artifacts": postprocess_strict_artifacts,
        },
    )
