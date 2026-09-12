"""Tests for solver-neutral durable run records."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.runtime.postprocess_phase import (
    CaseRecord,
    build_standalone_case_record,
    build_sweep_context,
    read_case_workflow_state,
    run_postprocess_phase,
    run_postprocessing_module,
    write_case_record,
)
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, write_manifest


def _manifest(root: Path, workflow_state_path: str = "case-a/outputs/workflow_state.json") -> None:
    write_manifest(root / "sweep_manifest.json", SweepManifest(
        schema_version="1.0", sweep_spec_hash="sha256:plan", created_at="start", updated_at="end",
        cases=[CaseManifestEntry(
            case_id="case-a", resolved_axis_values={"stimulus": 1}, override_hash="sha256:input",
            run_document_path="case-a/run_document.json", workflow_state_path=workflow_state_path,
            status="completed", outcome="fresh", started_at="start", updated_at="end",
            case_record_path="case-a/case_record.json",
        )],
    ))


def test_context_records_execution_without_scanning_solver_output(tmp_path: Path) -> None:
    _manifest(tmp_path)
    case_dir = tmp_path / "case-a" / "outputs"
    case_dir.mkdir(parents=True)
    (case_dir / "workflow_state.json").write_text(json.dumps({"status": "completed"}))
    (case_dir / "processor0" / "0").mkdir(parents=True)
    (case_dir / "processor0" / "0" / "Vm").write_text("not for Core to read")
    (tmp_path / "case-a" / "run_document.json").write_text(json.dumps({"launch": {"caseRoot": "/case"}}))

    context = build_sweep_context(tmp_path)

    case = context.cases[0]
    assert case.status == "completed"
    assert case.case_output_dir == str(case_dir)
    assert case.case_root == "/case"
    assert "output_files" not in case.to_json()
    assert not (tmp_path / "case-a" / "case_record.json").exists()


def test_executor_can_explicitly_persist_case_records(tmp_path: Path) -> None:
    _manifest(tmp_path)
    context = build_sweep_context(tmp_path, persist_case_records=True)
    assert context.cases[0].status == "completed"
    assert json.loads((tmp_path / "case-a" / "case_record.json").read_text())["status"] == "completed"


def test_context_retains_output_location_even_if_output_was_deleted(tmp_path: Path) -> None:
    _manifest(tmp_path)
    context = build_sweep_context(tmp_path)
    assert context.cases[0].status == "completed"
    assert context.cases[0].case_output_dir == str(tmp_path / "case-a" / "outputs")


def test_workflow_state_is_the_core_execution_evidence(tmp_path: Path) -> None:
    _manifest(tmp_path)
    state_path = tmp_path / "case-a" / "outputs" / "workflow_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"status": "completed", "steps": [{"step_id": "solve"}]}))
    context = build_sweep_context(tmp_path)
    assert read_case_workflow_state(context, "case-a")["status"] == "completed"
    with pytest.raises(KeyError, match="unknown case_id"):
        read_case_workflow_state(context, "unknown")


def test_standalone_record_does_not_inventory_outputs(tmp_path: Path) -> None:
    (tmp_path / "workflow_state.json").write_text(json.dumps({"status": "completed"}))
    (tmp_path / "processor0").mkdir()
    record = build_standalone_case_record(
        entry="case", case_root=Path("/case"), setup_root=None, output_dir=tmp_path,
    )
    assert record.status == "completed"
    assert "output_files" not in record.to_json()


def test_core_postprocess_is_explicitly_not_configured(tmp_path: Path) -> None:
    _manifest(tmp_path)
    context = build_sweep_context(tmp_path)
    assert run_postprocess_phase(entry="case", output_dir=tmp_path).status == "not_configured"
    assert run_postprocessing_module(context, task="measure activation").status == "not_configured"


def test_case_record_write_has_only_declared_evidence(tmp_path: Path) -> None:
    record = CaseRecord(
        case_id="case", resolved_axis_values={}, status="completed", outcome="fresh",
        workflow_state_path="/state.json", case_output_dir="/out", setup_root=None,
    )
    path = tmp_path / "record.json"
    write_case_record(path, record)
    assert json.loads(path.read_text())["workflow_state_path"] == "/state.json"
