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

# core.quantities.comparison.CHECKER_ID. Not imported: that module imports
# ComparisonRequest from this one, so a module-level import here would be
# circular. `test_the_quantities_checker_id_constant_matches_core` guards
# against the two drifting apart (M6, controller review 2026-09-26).
_QUANTITIES_CHECKER_ID = "omnidriver.quantities"


@dataclass(frozen=True)
class ComparisonReportLimits:
    """Structural limits for a checker report envelope, not solver data."""

    max_bytes: int = 1_048_576
    max_metrics: int = 100
    max_detail_fields: int = 32
    max_nested_items: int = 20
    max_string_chars: int = 512
    max_depth: int = 4

    def __post_init__(self) -> None:
        if any(value < 1 for value in (
            self.max_bytes, self.max_metrics, self.max_detail_fields,
            self.max_nested_items, self.max_string_chars, self.max_depth,
        )):
            raise ValueError("comparison report limits must be positive")


DEFAULT_COMPARISON_REPORT_LIMITS = ComparisonReportLimits()


@dataclass(frozen=True)
class ComparisonRequest:
    """Identity and location of one already-produced checker report.

    The request intentionally cannot name a command.  Running a solver's
    checker is an adapter/test concern; this public Core interface only
    preserves its resulting evidence alongside the experiment it describes.
    ``report_path`` may be absolute, or relative to the experiment output
    directory. A report may declare ``run_evidence`` containing ``case_id``,
    ``workflow_digest``, and ``input_provenance_digest``. Core checks those
    identifiers against its durable run record; missing or mismatched evidence
    is reported as an unverified association, not a scientific failure.

    ``run_evidence`` may also be a list of such objects, for a report that
    compares several runs; the case is verified when exactly one entry
    matches it (added 2026-09-26).
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
    inspection without giving Core their scientific meaning. Core exposes a
    bounded summary only; ``report_path`` remains the reference to full
    checker-owned evidence.
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
    details_truncated: bool = False
    association_status: str = "not_requested"
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
        if self.details_truncated:
            payload["details_truncated"] = True
        payload["association_status"] = self.association_status
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
    comparison_limits: ComparisonReportLimits = DEFAULT_COMPARISON_REPORT_LIMITS,
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
        _inspect_case(
            context, case, requested.get(case.case_id),
            comparison_limits=comparison_limits,
        )
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
    context: SweepContext,
    record: CaseRecord,
    request: ComparisonRequest | None,
    *,
    comparison_limits: ComparisonReportLimits,
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
    comparison = _read_comparison(
        context, record, state, request, limits=comparison_limits,
    )
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


def _read_comparison(
    context: SweepContext,
    record: CaseRecord,
    state: Mapping[str, Any],
    request: ComparisonRequest | None,
    *,
    limits: ComparisonReportLimits,
) -> ComparisonOutcome:
    if request is None:
        return ComparisonOutcome(status="not_requested")
    report_path = Path(request.report_path)
    if not report_path.is_absolute():
        report_path = Path(context.output_dir) / report_path
    try:
        size = report_path.stat().st_size
        if size > limits.max_bytes:
            return ComparisonOutcome(
                status="unavailable",
                checker_id=request.checker_id,
                checker_version=request.checker_version,
                reference_id=request.reference_id,
                reference_version=request.reference_version,
                report_path=str(report_path),
                association_status="unverified",
                reason=(
                    f"checker report exceeds configured envelope limit "
                    f"({size} > {limits.max_bytes} bytes)"
                ),
            )
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
            association_status="unverified",
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
            association_status="unverified",
            reason="checker report must contain a JSON object",
        )
    stated_status = report.get("status")
    status = stated_status if isinstance(stated_status, str) and stated_status in _COMPARISON_STATUSES else "unknown"
    reason: str | None = None
    if request.checker_id == _QUANTITIES_CHECKER_ID:
        # M6, controller review 2026-09-26: never trust a checker
        # omnidriver.quantities report's stated status verbatim -- it is
        # written read-only, but nothing stops an edit after the fact, so
        # recompute it from the report's own metrics with the function that
        # wrote it in the first place.
        status, reason = _quantities_status(report, stated_status=status)
    metric_values, metric_truncated = _bounded_metrics(report.get("metrics"), limits)
    details, detail_truncated = _bounded_details(report, limits)
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
        details_truncated=metric_truncated or detail_truncated,
        association_status=_association_status(report, record, state),
        reason=reason,
    )


def _quantities_status(report: Mapping[str, Any], *, stated_status: str) -> tuple[str, str | None]:
    """Recompute a checker ``omnidriver.quantities`` report's overall status
    from its own ``metrics`` and ``both_not_reached``, using the same
    function that wrote it (``core.quantities.comparison.overall_status``,
    imported lazily here to avoid the cycle noted at ``_QUANTITIES_CHECKER_ID``).
    A report that cannot be recomputed at all, or recomputes to something
    other than what it states, is a named failure -- never a silent
    pass-through of whatever ``status`` says (M6, controller review
    2026-09-26)."""
    from .quantities.comparison import overall_status

    metrics = report.get("metrics")
    if not isinstance(metrics, list) or not metrics or any(
        not isinstance(metric, Mapping) or not isinstance(metric.get("status"), str) for metric in metrics
    ):
        return "failed", "checker omnidriver.quantities report has no recomputable metrics; its status cannot be trusted"
    both_not_reached = report.get("both_not_reached")
    if not isinstance(both_not_reached, str):
        return "failed", "checker omnidriver.quantities report declares no both_not_reached; its status cannot be trusted"
    try:
        recomputed, recompute_reason = overall_status(
            (metric["status"] for metric in metrics), both_not_reached=both_not_reached,
        )
    except ValueError as exc:
        return "failed", f"checker omnidriver.quantities report cannot be recomputed: {exc}"
    if recomputed != stated_status:
        return "failed", (
            f"checker omnidriver.quantities reported status {stated_status!r}, but recomputing from its own metrics "
            f"gives {recomputed!r}; the report may have been edited after it was written"
        )
    return stated_status, recompute_reason


def _association_status(
    report: Mapping[str, Any], record: CaseRecord, state: Mapping[str, Any],
) -> str:
    """Verify a declared run identity; Core never verifies solver outputs."""
    evidence = report.get("run_evidence")
    snapshot = state.get("resume_snapshot")
    expected = {
        "case_id": record.case_id,
        "workflow_digest": state.get("workflow_digest"),
        "input_provenance_digest": (
            snapshot.get("aggregate_digest") if isinstance(snapshot, Mapping) else None
        ),
    }
    if isinstance(evidence, list):
        # A report comparing several runs (core.quantities, added 2026-09-26)
        # lists one evidence object per run; this case is verified when
        # exactly one entry carries all three of its identifiers.
        matches = [item for item in evidence if isinstance(item, Mapping)
                   and all(item.get(key) == value for key, value in expected.items())]
        evidence = matches[0] if len(matches) == 1 else None
    if not isinstance(evidence, Mapping) or any(not isinstance(value, str) for value in expected.values()):
        return "unverified"
    return "run_verified" if all(evidence.get(key) == value for key, value in expected.items()) else "unverified"


def _bounded_metrics(
    raw_metrics: Any, limits: ComparisonReportLimits,
) -> tuple[tuple[dict[str, Any], ...], bool]:
    if not isinstance(raw_metrics, list):
        return (), raw_metrics is not None
    truncated = len(raw_metrics) > limits.max_metrics
    metrics: list[dict[str, Any]] = []
    for item in raw_metrics[:limits.max_metrics]:
        if not isinstance(item, Mapping):
            truncated = True
            continue
        summary, item_truncated = _bounded_json(item, limits=limits)
        metrics.append(dict(summary))
        truncated = truncated or item_truncated
    return tuple(metrics), truncated


def _bounded_details(
    report: Mapping[str, Any], limits: ComparisonReportLimits,
) -> tuple[dict[str, Any], bool]:
    items = [
        (key, value) for key, value in report.items()
        if key not in {"status", "metrics", "run_evidence"}
    ]
    truncated = len(items) > limits.max_detail_fields
    details: dict[str, Any] = {}
    for key, value in items[:limits.max_detail_fields]:
        summary, value_truncated = _bounded_json(value, limits=limits)
        details[str(key)] = summary
        truncated = truncated or value_truncated
    return details, truncated


def _bounded_json(
    value: Any, *, limits: ComparisonReportLimits, depth: int = 0,
) -> tuple[Any, bool]:
    if value is None or isinstance(value, (bool, int, float)):
        return value, False
    if isinstance(value, str):
        if len(value) <= limits.max_string_chars:
            return value, False
        return value[:limits.max_string_chars] + "…", True
    if depth >= limits.max_depth:
        return "<nested value omitted>", True
    if isinstance(value, Mapping):
        items = list(value.items())
        result: dict[str, Any] = {}
        truncated = len(items) > limits.max_nested_items
        for key, child in items[:limits.max_nested_items]:
            summary, child_truncated = _bounded_json(child, limits=limits, depth=depth + 1)
            result[str(key)] = summary
            truncated = truncated or child_truncated
        return result, truncated
    if isinstance(value, list):
        result: list[Any] = []
        truncated = len(value) > limits.max_nested_items
        for child in value[:limits.max_nested_items]:
            summary, child_truncated = _bounded_json(child, limits=limits, depth=depth + 1)
            result.append(summary)
            truncated = truncated or child_truncated
        return result, truncated
    return "<unsupported JSON value>", True


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
