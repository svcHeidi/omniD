"""Tests for solver-neutral durable run records."""
from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.runtime.case_records import (
    CaseRecord,
    build_standalone_case_record,
    build_sweep_context,
    sweep_case_record,
    write_case_record,
)
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, read_manifest, write_manifest


def _manifest(
    root: Path, workflow_state_path: str = "case-a/outputs/workflow_state.json", sweep_outcome: str = "completed",
) -> None:
    write_manifest(root / "sweep_manifest.json", SweepManifest(
        schema_version="1.0", sweep_spec_hash="sha256:plan", created_at="start", updated_at="end",
        cases=[CaseManifestEntry(
            case_id="case-a", resolved_axis_values={"stimulus": 1}, override_hash="sha256:input",
            run_document_path="case-a/run_document.json", workflow_state_path=workflow_state_path,
            sweep_outcome=sweep_outcome, outcome="fresh", started_at="start", updated_at="end",
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


def test_a_sweep_case_record_is_identity_and_locations_relative_to_its_own_folder(tmp_path: Path) -> None:
    _manifest(tmp_path)
    (tmp_path / "case-a").mkdir()
    (tmp_path / "case-a" / "run_document.json").write_text(
        json.dumps({"launch": {"caseRoot": str(tmp_path / "case-a"), "setupRoot": str(tmp_path / "setup")}}),
    )
    entry = read_manifest(tmp_path / "sweep_manifest.json").cases[0]

    write_case_record(tmp_path / entry.case_record_path, sweep_case_record(entry, tmp_path))

    record = json.loads((tmp_path / "case-a" / "case_record.json").read_text())
    assert "status" not in record and "updated_at" not in record
    assert (record["case_id"], record["resolved_axis_values"]) == ("case-a", {"stimulus": 1})
    assert record["workflow_state_path"] == "outputs/workflow_state.json"
    assert record["run_document_path"] == "run_document.json"
    assert (record["case_root"], record["setup_root"]) == (".", "../setup")


def test_context_reads_the_status_the_case_has_now_not_the_one_the_sweep_saw(tmp_path: Path) -> None:
    """A case a later ``step`` completed is completed for ``compare``, whatever the manifest recorded."""
    _manifest(tmp_path, sweep_outcome="failed")
    state = tmp_path / "case-a" / "outputs" / "workflow_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "completed"}))

    context = build_sweep_context(tmp_path)

    assert context.cases[0].status == "completed"
    assert (context.completed_count, context.failed_count) == (1, 0)


def test_a_case_with_no_workflow_state_never_ran_whatever_the_sweep_observed(tmp_path: Path) -> None:
    _manifest(tmp_path, sweep_outcome="completed")
    context = build_sweep_context(tmp_path)
    assert (context.cases[0].status, context.completed_count, context.failed_count) == ("not_run", 0, 1)


def test_the_context_never_writes_a_record(tmp_path: Path) -> None:
    _manifest(tmp_path)
    build_sweep_context(tmp_path)
    assert not (tmp_path / "case-a" / "case_record.json").exists()


def test_context_retains_output_location_even_if_output_was_deleted(tmp_path: Path) -> None:
    _manifest(tmp_path)
    context = build_sweep_context(tmp_path)
    assert context.cases[0].case_output_dir == str(tmp_path / "case-a" / "outputs")


def test_standalone_record_does_not_inventory_outputs(tmp_path: Path) -> None:
    (tmp_path / "processor0").mkdir()
    record = build_standalone_case_record(
        entry="case", case_root=tmp_path / "case", setup_root=None, output_dir=tmp_path,
    )
    assert record.workflow_state_path == "workflow_state.json"
    assert (record.case_root, record.setup_root) == ("case", None)
    assert "output_files" not in record.to_json() and "status" not in record.to_json()


def test_case_record_write_has_only_declared_evidence(tmp_path: Path) -> None:
    record = CaseRecord(
        case_id="case", resolved_axis_values={}, outcome="fresh",
        workflow_state_path="state.json", case_output_dir="out", setup_root=None,
    )
    path = tmp_path / "record.json"
    write_case_record(path, record)
    assert json.loads(path.read_text())["workflow_state_path"] == "state.json"
