"""Public, solver-neutral read model for completed simulation experiments.

``sweep_run`` remains the only sweep executor.  This module makes its durable
manifest, RunDocuments, and workflow states useful after execution without
asking an agent to reconstruct a simulation from directories and log files.

The boundary is deliberate:

* Core reports what was requested, planned, and executed.
* A plugin or solver-owned checker supplies scientific comparison evidence.
* Core records a checker's stated status and its declared metrics, but never
  decides whether a numerical difference is scientifically acceptable.

All comparison inputs are explicit.  Reading an experiment never discovers or
executes a convenient ``regressionTest.sh`` beside a case.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .runtime.postprocess_phase import CaseRecord, SweepContext, build_sweep_context
from .runtime.sweep_runner import sweep_run


_COMPARISON_STATUSES = frozenset({"passed", "failed", "unavailable", "not_requested", "unknown"})


@dataclass(frozen=True)
class ComparisonRequest:
    """Identity and location of one already-produced checker report.

    The request intentionally cannot name a command.  Running a solver's
    checker is an adapter/test concern; this public Core interface only
    preserves its resulting evidence alongside the experiment it describes.
    ``report_path`` may be absolute, or relative to the experiment output
    directory.
    """

    case_id: str
    checker_id: str
    checker_version: str
    reference_id: str
    reference_version: str
    report_path: str


@dataclass(frozen=True)
class ComparisonOutcome:
    """An optional, solver-supplied result comparison.

    ``metrics`` is only a pass-through of a report's declared ``metrics``
    list.
    Its names, units, definitions, and values belong to the checker or
    analysis adapter.  ``details`` preserves other report fields for
    inspection without giving Core their scientific meaning.
    """

    status: str
    checker_id: str | None = None
    checker_version: str | None = None
    reference_id: str | None = None
    reference_version: str | None = None
    report_path: str | None = None
    report_digest: str | None = None
    metrics: tuple[dict[str, Any], ...] = ()
    details: dict[str, Any] | None = None
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "metrics": [dict(metric) for metric in self.metrics],
        }
        for key in (
            "checker_id", "checker_version", "reference_id", "reference_version",
            "report_path", "report_digest", "details", "reason",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class ExperimentCase:
    """One attributable trial within a sweep experiment."""

    case_id: str
    requested_parameters: dict[str, Any]
    execution_status: str
    execution_steps: tuple[dict[str, Any], ...]
    plan_identity: str | None
    input_provenance: dict[str, Any] | None
    expected_artifacts: tuple[dict[str, Any], ...]
    output_status: str
    output_directory: str | None
    comparison: ComparisonOutcome

    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "requested_parameters": dict(self.requested_parameters),
            "execution": {
                "status": self.execution_status,
                "steps": [dict(step) for step in self.execution_steps],
                "plan_identity": self.plan_identity,
                "input_provenance": self.input_provenance,
            },
            "outputs": {
                "status": self.output_status,
                "directory": self.output_directory,
                "expected_artifacts": [dict(artifact) for artifact in self.expected_artifacts],
            },
            "comparison": self.comparison.to_json(),
        }


@dataclass(frozen=True)
class Experiment:
    """A completed or partial sweep in an agent-readable form."""

    schema_version: int
    output_directory: str
    experiment_identity: str
    started_at: str
    updated_at: str
    cases: tuple[ExperimentCase, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "output_directory": self.output_directory,
            "experiment_identity": self.experiment_identity,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "summary": {
                "case_count": len(self.cases),
                "execution": _status_counts(case.execution_status for case in self.cases),
                "outputs": _status_counts(case.output_status for case in self.cases),
                "comparisons": _status_counts(case.comparison.status for case in self.cases),
            },
            "cases": [case.to_json() for case in self.cases],
        }


def run_sweep_experiment(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run an experiment through the existing ``sweep_run`` implementation.

    This is a public name for the established execution path, not a second
    runner.  Its arguments and execution behavior are exactly ``sweep_run``.
    """

    return sweep_run(*args, **kwargs)


def inspect_sweep_experiment(
    output_dir: str | Path,
    *,
    comparisons: Iterable[ComparisonRequest] = (),
) -> Experiment:
    """Read one sweep's durable evidence and optional comparison reports.

    Core reports its durable execution evidence and opaque output locations.
    It does not inspect solver output trees. An adapter may later attach a
    declared output inspection or analysis result.
    """

    output_dir = Path(output_dir)
    context = build_sweep_context(output_dir)
    requested = _comparison_requests_by_case(comparisons, context)
    cases = tuple(
        _inspect_case(context, case, requested.get(case.case_id))
        for case in context.cases
    )
    return Experiment(
        schema_version=1,
        output_directory=str(output_dir),
        experiment_identity=context.sweep_spec_hash,
        started_at=context.started_at,
        updated_at=context.finished_at,
        cases=cases,
    )


def load_comparison_requests(path: str | Path) -> tuple[ComparisonRequest, ...]:
    """Load explicit comparison declarations from a small JSON manifest.

    The manifest has ``{"schema_version": 1, "comparisons": [...]}``.
    Every declaration records checker and reference identities so a passing
    exit code cannot be separated from the criterion that produced it.
    """

    path = Path(path)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid comparison manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("comparison manifest requires schema_version 1")
    raw_requests = payload.get("comparisons")
    if not isinstance(raw_requests, list):
        raise ValueError("comparison manifest requires a comparisons list")
    requests: list[ComparisonRequest] = []
    for index, raw in enumerate(raw_requests):
        if not isinstance(raw, dict):
            raise ValueError(f"comparison {index} must be an object")
        fields = (
            "case_id", "checker_id", "checker_version", "reference_id",
            "reference_version", "report_path",
        )
        if any(not isinstance(raw.get(field), str) or not raw[field] for field in fields):
            raise ValueError(f"comparison {index} requires non-empty string identity fields")
        requests.append(ComparisonRequest(**{field: raw[field] for field in fields}))
    return tuple(requests)


def _comparison_requests_by_case(
    requests: Iterable[ComparisonRequest], context: SweepContext,
) -> dict[str, ComparisonRequest]:
    case_ids = {case.case_id for case in context.cases}
    result: dict[str, ComparisonRequest] = {}
    for request in requests:
        if request.case_id not in case_ids:
            raise ValueError(f"comparison names unknown experiment case {request.case_id!r}")
        if request.case_id in result:
            raise ValueError(f"comparison is declared more than once for case {request.case_id!r}")
        result[request.case_id] = request
    return result


def _inspect_case(
    context: SweepContext, record: CaseRecord, request: ComparisonRequest | None,
) -> ExperimentCase:
    state = _read_json_object(Path(record.workflow_state_path))
    execution_status = str(state.get("status", record.status)) if state else record.status
    steps = tuple(
        dict(step) for step in state.get("steps", ())
        if isinstance(step, dict)
    ) if state else ()
    resume_snapshot = state.get("resume_snapshot") if state else None
    input_provenance = dict(resume_snapshot) if isinstance(resume_snapshot, dict) else None
    workflow_digest = state.get("workflow_digest") if state else None
    expected_artifacts = _expected_artifacts(context, record)
    comparison = _read_comparison(context, request)
    return ExperimentCase(
        case_id=record.case_id,
        requested_parameters=dict(record.resolved_axis_values),
        execution_status=execution_status,
        execution_steps=steps,
        plan_identity=str(workflow_digest) if workflow_digest else None,
        input_provenance=input_provenance,
        expected_artifacts=expected_artifacts,
        output_status=_output_status(record, execution_status),
        output_directory=record.case_output_dir,
        comparison=comparison,
    )


def _expected_artifacts(context: SweepContext, record: CaseRecord) -> tuple[dict[str, Any], ...]:
    if not record.run_document_path:
        return ()
    path = Path(record.run_document_path)
    path = path if path.is_absolute() else Path(context.output_dir) / path
    document = _read_json_object(path)
    raw_artifacts = document.get("expectedArtifacts", ())
    if not isinstance(raw_artifacts, list):
        return ()
    return tuple(dict(item) for item in raw_artifacts if isinstance(item, dict))


def _output_status(record: CaseRecord, execution_status: str) -> str:
    del execution_status
    if record.case_output_dir is None:
        return "unavailable"
    return "not_inspected"


def _read_comparison(context: SweepContext, request: ComparisonRequest | None) -> ComparisonOutcome:
    if request is None:
        return ComparisonOutcome(status="not_requested")
    report_path = Path(request.report_path)
    if not report_path.is_absolute():
        report_path = Path(context.output_dir) / report_path
    try:
        raw_bytes = report_path.read_bytes()
        report = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        return ComparisonOutcome(
            status="unavailable",
            checker_id=request.checker_id,
            checker_version=request.checker_version,
            reference_id=request.reference_id,
            reference_version=request.reference_version,
            report_path=str(report_path),
            reason=f"checker report unavailable: {type(exc).__name__}: {exc}",
        )
    if not isinstance(report, dict):
        return ComparisonOutcome(
            status="unavailable",
            checker_id=request.checker_id,
            checker_version=request.checker_version,
            reference_id=request.reference_id,
            reference_version=request.reference_version,
            report_path=str(report_path),
            reason="checker report must contain a JSON object",
        )
    stated_status = report.get("status")
    status = stated_status if isinstance(stated_status, str) and stated_status in _COMPARISON_STATUSES else "unknown"
    metrics = report.get("metrics", ())
    metric_values = tuple(dict(item) for item in metrics if isinstance(item, dict)) if isinstance(metrics, list) else ()
    details = {
        key: value for key, value in report.items()
        if key not in {"status", "metrics"}
    }
    return ComparisonOutcome(
        status=status,
        checker_id=request.checker_id,
        checker_version=request.checker_version,
        reference_id=request.reference_id,
        reference_version=request.reference_version,
        report_path=str(report_path),
        report_digest="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
        metrics=metric_values,
        details=details,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _status_counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
