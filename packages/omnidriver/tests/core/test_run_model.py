"""Tests for the Run document JSON Schema and ``RunDocument`` dataclass."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import jsonschema
import pytest

from omnidriver.core.runtime.run_model import RunDocument
from omnidriver.core.runtime.workflow_state import workflow_state_from_json


@pytest.fixture
def schema():
    return json.loads(
        resources.files("omnidriver.schemas").joinpath("run-document.json").read_text()
    )


def _valid_run_dict():
    return {
        "version": "3",
        "id": "run-0001",
        "name": "demo",
        "createdAt": "2026-04-20T10:00:00Z",
        "lastModified": "2026-04-20T10:00:00Z",
        "status": "draft",
        "validation": {},
        "resolvedEntry": None,
        "workflowDag": None,
        "workflowState": None,
        "launch": None,
        "expectedArtifacts": [],
        "terminalStatusValues": ["completed", "failed"],
    }


def test_schema_validates_minimal_valid_run(schema):
    jsonschema.validate(_valid_run_dict(), schema)  # does not raise


def test_schema_rejects_unknown_status(schema):
    bad = _valid_run_dict()
    bad["status"] = "nonsense"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_run_document_round_trip():
    doc = RunDocument.from_json(_valid_run_dict())
    back = doc.to_json()
    assert back["id"] == "run-0001"
    assert back["status"] == "draft"
    assert back["version"] == "3"




def test_schema_accepts_normalized_workflow_dag(schema):
    doc = _valid_run_dict()
    doc["workflowDag"] = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [
            {
                "id": "solve",
                "command": "cardiacFoam",
                "args": [],
                "cwd": ".",
                "depends_on": [],
                "produces": ["single_cell_trace"],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": "cardiacFoam",
            }
        ],
    }
    jsonschema.validate(doc, schema)  # does not raise


def test_schema_rejects_raw_workflow_step_shape(schema):
    doc = _valid_run_dict()
    doc["workflowDag"] = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [{"id": "solve", "command": "cardiacFoam"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_schema_accepts_initial_workflow_state(schema):
    doc = _valid_run_dict()
    doc["workflowState"] = {
        "status": "pending",
        "current_step_id": "solve",
        "completed_steps": [],
        "failed_step_id": None,
        "steps": [
            {
                "step_id": "solve",
                "status": "pending",
                "attempt": 0,
                "command": "cardiacFoam",
                "args": [],
                "cwd": ".",
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "stdout_log": None,
                "stderr_log": None,
                "produced_artifacts": [],
                "diagnostics": [],
            }
        ],
    }
    jsonschema.validate(doc, schema)  # does not raise


def test_schema_accepts_serialized_workflow_identity_and_resume_evidence(schema):
    doc = _valid_run_dict()
    doc["workflowState"] = {
        "status": "completed",
        "current_step_id": None,
        "completed_steps": [],
        "failed_step_id": None,
        "steps": [],
        "workflow_digest": "sha256:" + "a" * 64,
        "resume_snapshot": {
                "schema_version": "2.4-sha256-streaming-256mib-verified-absence-stable-env",
            "components": [{
                "kind": "file",
                "path": "system/controlDict",
                "role": "required_input",
                "origin": "case",
                "method": "sha256",
                "strength": "content",
                "digest": "sha256:" + "e" * 64,
                "size": 1,
                "mtime_ns": 0,
                "link_target": None,
            }],
            "workflow_digest": "sha256:" + "a" * 64,
            # StackIdentity.to_json() (core.provider_identity) plus the
            # environment_digest that runtime.resume.checkpoint_snapshot adds
            # -- not a flat PluginIdentity shape.
            "plugin_identity": {
                "providers": [{
                    "id": "org.example.test",
                    "version": "1",
                    "api_version": "1",
                    "source": "test",
                    "provider_digest": "sha256:" + "e" * 64,
                }],
                "composition_rule_version": "1",
                "capability_digest": "b" * 64,
                "resolutions": {"command_authorization": "org.example.test"},
                "environment_digest": "c" * 64,
            },
            "aggregate_digest": "sha256:" + "d" * 64,
            "is_complete": True,
        },
    }

    jsonschema.validate(doc, schema)
    assert workflow_state_from_json(doc["workflowState"]).to_json() == doc["workflowState"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workflow_digest", "not-a-digest"),
        ("resume_snapshot", {"unexpected": "shape"}),
        ("unexpected", True),
    ],
)
def test_schema_rejects_malformed_workflow_identity_evidence(schema, field, value):
    doc = _valid_run_dict()
    doc["workflowState"] = {
        "status": "pending",
        "current_step_id": None,
        "completed_steps": [],
        "failed_step_id": None,
        "steps": [],
        field: value,
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_schema_rejects_unknown_workflow_state_status(schema):
    doc = _valid_run_dict()
    doc["workflowState"] = {
        "status": "waiting",
        "current_step_id": None,
        "completed_steps": [],
        "failed_step_id": None,
        "steps": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


@pytest.mark.parametrize("version", ["1", "2"])
def test_run_document_refuses_any_version_but_3(version):
    old = _valid_run_dict()
    old["version"] = version
    with pytest.raises(jsonschema.ValidationError):
        RunDocument.from_json(old)


def test_core_declares_no_phase_vocabulary() -> None:
    """Neither module may spell a solver's editing phases."""
    from omnidriver.core.contracts import dictionary
    from omnidriver.core.runtime import run_model

    assert not hasattr(dictionary, "Phase")
    assert not hasattr(run_model, "Phase")


@pytest.mark.parametrize("retired", ["config", "configurationSource"])
def test_a_document_carrying_a_retired_field_is_refused_not_translated(retired):
    old = _valid_run_dict()
    old[retired] = {} if retired == "config" else "document"
    with pytest.raises(jsonschema.ValidationError):
        RunDocument.from_json(old)
