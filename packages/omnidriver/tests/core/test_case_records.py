"""Tests for solver-neutral durable run records."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.runtime.case_records import (
    CaseRecord,
    build_standalone_case_record,
    build_sweep_context,
    read_case_record,
    refresh_case_record,
    sweep_case_record,
    write_case_record,
)
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, read_manifest, write_manifest


def _manifest(
    root: Path, workflow_state_path: str = "case-a/outputs/workflow_state.json", status: str = "completed",
) -> None:
    write_manifest(root / "sweep_manifest.json", SweepManifest(
        schema_version="1.0", sweep_spec_hash="sha256:plan", created_at="start", updated_at="end",
        cases=[CaseManifestEntry(
            case_id="case-a", resolved_axis_values={"stimulus": 1}, override_hash="sha256:input",
            run_document_path="case-a/run_document.json", workflow_state_path=workflow_state_path,
            status=status, outcome="fresh", started_at="start", updated_at="end",
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


def test_a_sweep_case_record_is_written_where_the_manifest_says(tmp_path: Path) -> None:
    _manifest(tmp_path)
    manifest = read_manifest(tmp_path / "sweep_manifest.json")
    entry = manifest.cases[0]
    write_case_record(tmp_path / entry.case_record_path, sweep_case_record(entry, tmp_path))
    assert json.loads((tmp_path / "case-a" / "case_record.json").read_text())["status"] == "completed"


def test_context_reads_the_status_the_case_has_now_not_the_one_the_sweep_saw(tmp_path: Path) -> None:
    """A case a later ``step`` completed is completed for ``compare``, whatever the manifest recorded."""
    _manifest(tmp_path, status="failed")
    state = tmp_path / "case-a" / "outputs" / "workflow_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "completed"}))

    context = build_sweep_context(tmp_path)

    assert context.cases[0].status == "completed"
    assert (context.completed_count, context.failed_count) == (1, 0)


def test_context_falls_back_to_the_manifest_when_the_case_has_no_state(tmp_path: Path) -> None:
    _manifest(tmp_path, status="failed")
    context = build_sweep_context(tmp_path)
    assert (context.cases[0].status, context.failed_count) == ("failed", 1)


def test_a_run_in_a_sweep_case_keeps_the_identity_of_its_record(tmp_path: Path) -> None:
    """The record a sweep wrote and the one a later run refreshes are one record: same case id and axis values."""
    (tmp_path / "workflow_state.json").write_text(json.dumps({"status": "completed"}))
    write_case_record(tmp_path / "case_record.json", CaseRecord(
        case_id="case_0001", resolved_axis_values={"dx": 1}, status="failed", outcome="fresh",
        workflow_state_path=str(tmp_path / "workflow_state.json"), case_output_dir=str(tmp_path), setup_root=None,
    ))

    record = build_standalone_case_record(entry="entryName", case_root=tmp_path, setup_root=None, output_dir=tmp_path)

    assert (record.case_id, record.resolved_axis_values, record.status) == ("case_0001", {"dx": 1}, "completed")


def test_refreshing_updates_only_an_existing_record(tmp_path: Path) -> None:
    (tmp_path / "workflow_state.json").write_text(json.dumps({"status": "completed"}))
    refresh_case_record(tmp_path)
    assert read_case_record(tmp_path / "case_record.json") is None
    write_case_record(tmp_path / "case_record.json", CaseRecord(
        case_id="c", resolved_axis_values={}, status="failed", outcome="fresh",
        workflow_state_path="s", case_output_dir=str(tmp_path), setup_root=None,
    ))

    refresh_case_record(tmp_path)

    assert read_case_record(tmp_path / "case_record.json").status == "completed"


def test_context_retains_output_location_even_if_output_was_deleted(tmp_path: Path) -> None:
    _manifest(tmp_path)
    context = build_sweep_context(tmp_path)
    assert context.cases[0].status == "completed"
    assert context.cases[0].case_output_dir == str(tmp_path / "case-a" / "outputs")


def test_standalone_record_does_not_inventory_outputs(tmp_path: Path) -> None:
    (tmp_path / "workflow_state.json").write_text(json.dumps({"status": "completed"}))
    (tmp_path / "processor0").mkdir()
    record = build_standalone_case_record(
        entry="case", case_root=Path("/case"), setup_root=None, output_dir=tmp_path,
    )
    assert record.status == "completed"
    assert "output_files" not in record.to_json()


def test_case_record_write_has_only_declared_evidence(tmp_path: Path) -> None:
    record = CaseRecord(
        case_id="case", resolved_axis_values={}, status="completed", outcome="fresh",
        workflow_state_path="/state.json", case_output_dir="/out", setup_root=None,
    )
    path = tmp_path / "record.json"
    write_case_record(path, record)
    assert json.loads(path.read_text())["workflow_state_path"] == "/state.json"
