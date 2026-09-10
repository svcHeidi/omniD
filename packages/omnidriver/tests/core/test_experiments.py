from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.experiments import (
    ComparisonRequest,
    inspect_sweep_experiment,
    load_comparison_requests,
)
from omnidriver.core.runtime.sweep_manifest import (
    CaseManifestEntry,
    SweepManifest,
    write_manifest,
)


def _manifest(output_dir: Path, cases: list[CaseManifestEntry]) -> None:
    write_manifest(
        output_dir / "sweep_manifest.json",
        SweepManifest(
            schema_version="1.0",
            sweep_spec_hash="sha256:experiment",
            created_at="2026-09-10T12:00:00+00:00",
            updated_at="2026-09-10T12:01:00+00:00",
            cases=cases,
        ),
    )


def _case(output_dir: Path, case_id: str, *, status: str) -> CaseManifestEntry:
    case_dir = output_dir / case_id
    state_dir = case_dir / "outputs"
    state_dir.mkdir(parents=True)
    (state_dir / "result.txt").write_text(f"result for {case_id}\n")
    (state_dir / "workflow_state.json").write_text(json.dumps({
        "status": status,
        "workflow_digest": f"sha256:plan-{case_id}",
        "resume_snapshot": {"aggregate_digest": f"sha256:inputs-{case_id}"},
        "steps": [{"step_id": "solve", "status": status, "attempt": 1}],
    }))
    (case_dir / "run_document.json").write_text(json.dumps({
        "expectedArtifacts": [{
            "artifact_id": "trace",
            "path_pattern": "results/trace.dat",
            "format": "table",
        }],
    }))
    return CaseManifestEntry(
        case_id=case_id,
        resolved_axis_values={"stimulus_amplitude": 55 if case_id == "a" else 60},
        override_hash=f"sha256:override-{case_id}",
        run_document_path=f"{case_id}/run_document.json",
        workflow_state_path=f"{case_id}/outputs/workflow_state.json",
        status=status,
        outcome="fresh",
        started_at="2026-09-10T12:00:00+00:00",
        updated_at="2026-09-10T12:01:00+00:00",
        case_record_path=f"{case_id}/case_record.json",
    )


def test_inspect_experiment_separates_execution_outputs_and_optional_comparison(tmp_path: Path) -> None:
    _manifest(tmp_path, [
        _case(tmp_path, "a", status="completed"),
        _case(tmp_path, "b", status="failed"),
    ])

    experiment = inspect_sweep_experiment(tmp_path)
    payload = experiment.to_json()

    assert payload["experiment_identity"] == "sha256:experiment"
    assert payload["summary"] == {
        "case_count": 2,
        "execution": {"completed": 1, "failed": 1},
        "outputs": {"complete": 1, "incomplete": 1},
        "comparisons": {"not_requested": 2},
    }
    completed, failed = experiment.cases
    assert completed.requested_parameters == {"stimulus_amplitude": 55}
    assert completed.plan_identity == "sha256:plan-a"
    assert completed.input_provenance == {"aggregate_digest": "sha256:inputs-a"}
    assert completed.output_status == "complete"
    assert completed.comparison.status == "not_requested"
    assert failed.execution_status == "failed"
    assert failed.output_status == "incomplete"


def test_inspect_experiment_records_but_does_not_interpret_checker_metrics(tmp_path: Path) -> None:
    _manifest(tmp_path, [_case(tmp_path, "a", status="completed")])
    report = tmp_path / "reports" / "checker.json"
    report.parent.mkdir()
    report.write_text(json.dumps({
        "status": "passed",
        "metrics": [{
            "id": "activation_time_ms",
            "value": 91.2,
            "unit": "ms",
            "definition": "solver-owned activation-time criterion",
        }],
        "tolerance": 0.5,
        "results": [{"status": "passed", "difference": 0.1}],
    }))

    experiment = inspect_sweep_experiment(tmp_path, comparisons=[ComparisonRequest(
        case_id="a",
        checker_id="cardiacfoam.regression",
        checker_version="3aa4b48",
        reference_id="single-cell-tworld",
        reference_version="reference-v1",
        report_path="reports/checker.json",
    )])
    comparison = experiment.cases[0].comparison

    assert comparison.status == "passed"
    assert comparison.checker_id == "cardiacfoam.regression"
    assert comparison.metrics == ({
        "id": "activation_time_ms",
        "value": 91.2,
        "unit": "ms",
        "definition": "solver-owned activation-time criterion",
    },)
    assert comparison.details == {
        "tolerance": 0.5,
        "results": [{"status": "passed", "difference": 0.1}],
    }
    assert comparison.report_digest and comparison.report_digest.startswith("sha256:")


def test_comparison_manifest_requires_explicit_checker_and_reference_identity(tmp_path: Path) -> None:
    manifest = tmp_path / "comparisons.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "comparisons": [{
            "case_id": "a",
            "checker_id": "solver.checker",
            "checker_version": "1.0",
            "reference_id": "reference-a",
            "reference_version": "2026-09",
            "report_path": "reports/a.json",
        }],
    }))

    assert load_comparison_requests(manifest) == (ComparisonRequest(
        case_id="a",
        checker_id="solver.checker",
        checker_version="1.0",
        reference_id="reference-a",
        reference_version="2026-09",
        report_path="reports/a.json",
    ),)

    manifest.write_text(json.dumps({"schema_version": 1, "comparisons": [{"case_id": "a"}]}))
    with pytest.raises(ValueError, match="identity fields"):
        load_comparison_requests(manifest)


def test_comparison_for_unknown_case_is_rejected(tmp_path: Path) -> None:
    _manifest(tmp_path, [_case(tmp_path, "a", status="completed")])
    with pytest.raises(ValueError, match="unknown experiment case"):
        inspect_sweep_experiment(tmp_path, comparisons=[ComparisonRequest(
            case_id="not-a-case",
            checker_id="checker",
            checker_version="1",
            reference_id="reference",
            reference_version="1",
            report_path="missing.json",
        )])
