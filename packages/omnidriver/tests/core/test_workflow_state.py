from __future__ import annotations

import re

from omnidriver.core.runtime.workflow_state import (
    initial_workflow_state,
    workflow_state_from_json,
)


def test_initial_workflow_state_marks_all_steps_pending() -> None:
    state = initial_workflow_state({
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [
            {
                "id": "mesh",
                "command": "blockMesh",
                "args": [],
                "cwd": ".",
                "depends_on": [],
                "produces": [],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": "blockMesh",
            },
            {
                "id": "solve",
                "command": "cardiacFoam",
                "args": [],
                "cwd": ".",
                "depends_on": ["mesh"],
                "produces": ["vm_series"],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": "cardiacFoam",
            },
        ],
    })

    assert state is not None
    payload = state.to_json()
    assert payload["status"] == "pending"
    assert payload["current_step_id"] == "mesh"
    assert payload["completed_steps"] == []
    assert payload["failed_step_id"] is None
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["workflow_digest"])
    assert [step["status"] for step in payload["steps"]] == ["pending", "pending"]
    assert [step["attempt"] for step in payload["steps"]] == [0, 0]
    assert [step["step_id"] for step in payload["steps"]] == ["mesh", "solve"]
    assert workflow_state_from_json(payload).to_json() == payload


def test_workflow_state_round_trips_resume_evidence() -> None:
    payload = {
        "status": "completed",
        "current_step_id": None,
        "completed_steps": [],
        "failed_step_id": None,
        "steps": [],
        "workflow_digest": "sha256:" + "a" * 64,
        "resume_snapshot": {
            "schema_version": "2.1-sha256-256mib",
            "components": [],
            "workflow_digest": "sha256:" + "a" * 64,
            "plugin_identity": {
                "id": "org.example.test",
                "version": "1",
                "api_version": "1",
                "source": "test",
                "capability_digest": "sha256:" + "b" * 64,
                "environment_digest": "c" * 64,
            },
            "aggregate_digest": "sha256:" + "d" * 64,
            "is_complete": True,
        },
    }

    assert workflow_state_from_json(payload).to_json() == payload


def test_initial_workflow_state_returns_none_without_steps() -> None:
    assert initial_workflow_state(None) is None
    assert initial_workflow_state({"steps": []}) is None
