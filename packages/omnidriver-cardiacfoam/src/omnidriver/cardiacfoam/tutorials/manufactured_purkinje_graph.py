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
#     manufactured_purkinje_graph
#
# Description
#     Defines the manufactured Purkinje graph convergence tutorial.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path
from typing import Sequence

from omnidriver.cardiacfoam.tutorials.defaults import manufactured_purkinje_graph as defaults
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.core.specs.common import resolve_spec_paths


def _build_cases(graph_ids: Sequence[str]) -> list[CaseConfig]:
    return [
        CaseConfig(
            case_id=str(graph_id),
            params={"graph_id": str(graph_id)},
        )
        for graph_id in graph_ids
    ]


def _apply_case(case_root: Path, case: CaseConfig) -> None:
    """This tutorial's entire mutation surface (Phase 3 Task 7).

    **Classification: source artifact, not a parameter.** `purkinjeGraph` is
    large geometric data (nodes, edges, conductance -- the same class of
    content `RenderedFile`'s own docstring calls out as "the global 'large
    assets are referenced by digest, never embedded' rule ... about meshes
    and VTU output"), not a small hand-editable dictionary key. It is copied
    verbatim, never key/value-patched, matching the identical pattern
    already accepted for `manufactured_monodomain_1d3d`'s own
    `purkinjeGraph.<id>` -> `purkinjeGraph` copy.

    **Corrected 2026-09-24 (review of Phase 3 Task 7): not a declared
    exception -- blocked on a missing channel capability, artifact staging.**
    This still stays a direct write, but the first-pass reasoning above
    ("forcing it through the channel would build a zero-`RenderedFile`
    plan, which `CaseWritePlan` refuses -- so this is a declared exception
    like `write_cell_set`") missed the actual cause. `CaseMutationRequest`'s
    own docstring already distinguishes what a source artifact IS (a
    reference: opaque, undigested, un-path-checked, "may legitimately live
    outside the case") from what it lacks: a way to *place* the referenced
    bytes at a case-relative destination. Phase 2's own plan anticipated
    both halves -- "large assets referenced by digest **and staged**" -- but
    only the reference half (`source_artifacts`, the `source_artifact`
    `Precondition` kind) was ever built; staging never was. So this copy
    stays direct not because it was decided to stay outside the channel
    (that is `write_cell_set`'s shape: one consumer, no second one yet, a
    real decision) but because the channel has no primitive for it yet -- a
    missing capability, buildable, tracked for Task 11 rather than declared
    settled here.
    """
    graph_id = str(case.params["graph_id"])
    source = case_root / "constant" / f"purkinjeGraph.{graph_id}"
    destination = case_root / "constant" / "purkinjeGraph"
    if not source.exists():
        raise FileNotFoundError(f"Missing graph file: {source}")
    shutil.copy2(source, destination)


def make_spec(
    *,
    cases_root: Path | None = None,
    tutorial_name: str = defaults.TUTORIAL_NAME,
    case_dir_name: str = defaults.CASE_DIR_NAME,
    setup_dir_name: str = defaults.SETUP_DIR_NAME,
    output_dir_name: str = defaults.OUTPUT_DIR_NAME,
    graph_ids: Sequence[str] = defaults.GRAPH_IDS,
    n_steps: int = defaults.N_STEPS,
    delta_t: float = defaults.DELTA_T,
    postprocess_strict_artifacts: bool = False,
) -> TutorialSpec:
    case_root, setup_root, output_dir = resolve_spec_paths(
        cases_root=cases_root,
        case_dir_name=case_dir_name,
        setup_dir_name=setup_dir_name,
        output_dir_name=output_dir_name,
        default_output_dir_name=defaults.OUTPUT_DIR_NAME,
    )
    graph_ids_list = [str(item) for item in graph_ids]

    return TutorialSpec(
        name=tutorial_name,
        case_root=case_root,
        setup_root=setup_root,
        output_dir=output_dir,
        build_cases=partial(_build_cases, graph_ids=graph_ids_list),
        apply_case=_apply_case,
        metadata={
            "notes": "Manufactured Purkinje graph convergence benchmark",
            # **Corrected 2026-09-23 (Phase 3 Task 7).** This module used to
            # also carry a private `_ensure_mesh(case_root, block_mesh_dict_
            # relpath)` helper that shelled out to `blockMesh` directly and
            # logged to `case_root/log.blockMesh` -- a framework-invoked
            # utility authoring `constant/polyMesh` (a case *input*, not a
            # declared workflow output) outside the DAG entirely. It had
            # zero callers anywhere in this repository (confirmed by
            # `grep -rn "_ensure_mesh"`, before this deletion, matching only
            # its own definition) and duplicated the "mesh" step already
            # declared right here -- the real, executed mechanism
            # (`workflow_orchestrator.py`/`workflow_runner.py` dispatch
            # `workflow_dag` steps; see `manufactured_eikonal_ecg.py`'s own
            # comment: "this lives on the workflow_dag path, which is the
            # mechanism sweep-run actually executes"). Deleted rather than
            # migrated: there was nothing live to migrate, since this "mesh"
            # step already is the declared, channel-external authoring of
            # `constant/polyMesh` that `_ensure_mesh` would otherwise have
            # needed to become.
            "workflow_dag": {
                "steps": [
                    {
                        "id": "mesh",
                        "command": "blockMesh",
                        "args": ["-dict", "system/blockMeshDict.3D"],
                        "depends_on": [],
                    },
                    {
                        "id": "solve",
                        "command": "runPurkinjeGraph",
                        "depends_on": ["mesh"],
                    },
                ]
            },
            "graph_ids": graph_ids_list,
            "n_steps": int(n_steps),
            "delta_t": float(delta_t),
            "control_dict_relpath": str(defaults.CONTROL_DICT_RELPATH),
            "electro_properties_relpath": str(defaults.ELECTRO_PROPERTIES_RELPATH),
            "postprocess_strict_artifacts": postprocess_strict_artifacts,
        },
    )
