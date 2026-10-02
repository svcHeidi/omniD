from __future__ import annotations

from typing import Any

from omnidriver.core.planning_types import artifact_to_json
from .models import DataArtifact
from .run_model import RunDocument
from .workflow_state import WorkflowRunState


def build_run_document(
    *,
    entry: str,
    spec,
    launch: dict[str, Any],
    workflow_dag: dict[str, Any] | None,
    workflow_state: WorkflowRunState | None,
    expected_artifacts: tuple[DataArtifact, ...],
    driver_context,
) -> RunDocument:
    return RunDocument(
        id=f"plan-{entry}",
        name=entry,
        status="planned",
        intent={"source": "strict_plan"},
        plugin=driver_context.identity.to_json(),
        resolvedEntry={
            "entry": entry,
            "entryPath": spec.metadata.get("entry_path"),
            # A record case run in parallel says so, with the scheduler
            # allocation checked against; a serial one carries no key.
            **({"parallel": spec.metadata["parallel"]} if "parallel" in spec.metadata else {}),
            # Every input this case resolved; absent when the record declares none.
            **({"inputs": spec.metadata["inputs"]} if "inputs" in spec.metadata else {}),
        },
        workflowDag=workflow_dag,
        workflowState=workflow_state.to_json() if workflow_state else None,
        launch={
            "action": launch.get("action"),
            "command": launch.get("command", []),
            "commandDisplay": launch.get("command_display", ""),
            "workflowStatePath": launch.get("workflow_state_path"),
            "caseRoot": launch.get("case_root"),
            "setupRoot": launch.get("setup_root"),
            "outputDir": launch.get("output_dir"),
        },
        expectedArtifacts=[artifact_to_json(artifact) for artifact in expected_artifacts],
        validation={"status": "not_run", "diagnostics": []},
    )
