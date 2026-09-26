"""Compare quantities read from runs, over pairs an agent states.

Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md.
Everything comes from the agent's request: which runs, which artifact of
each, where to sample (for a reader that samples at points), which
reference, which pairs, and the tolerance, declared before any value is
read. Core adds no frame conversion, pairing or tolerance of its own
(owner, 2026-09-26). The report shows every value with its unit, sampling
rule, sampled location and requested point, so a wrong pairing or
orientation is visible.

Order, so that nothing is decided after a value is seen:
1. the request and the reference are validated and digested;
2. every run's evidence, stack, artifact and reader are resolved, and every
   unit is checked convertible. A refusal here reads no artifact;
3. artifacts are read (sentinels resolved, then units converted) and the
   pairs compared, location first, then value;
4. the report is written once, to a path that must not exist.

The report is a checker report for ``experiments.inspect_sweep_experiment``:
``status``, ``metrics`` (one per pair) and ``run_evidence`` (one per run).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..experiments import ComparisonRequest
from ..plugin_interface import load_plugin_context
from ..provider_identity import stack_identity_mismatch
from ..runtime.models import DataArtifact, data_artifact_from_json
from ..runtime.postprocess_phase import CaseRecord, build_sweep_context
from ..runtime.reconciler import reconcile_artifacts
from .errors import QuantityComparisonError, QuantityError
from .model import Point, Quantity, ReadRequest, not_evaluated
from .reading import check_reader, converted, read_quantities
from .reference import PointReference, load_point_reference, schema_errors
from .units import check_convertible, convert

CHECKER_ID = "omnidriver.quantities"
CHECKER_VERSION = "1"
_FAILING = frozenset({"outside_tolerance", "reached_on_one_side", "sampled_off_point"})
_REQUEST_SCHEMA = json.loads(
    resources.files("omnidriver.schemas").joinpath("quantity-comparison.schema.json").read_text()
)


@dataclass(frozen=True)
class Tolerance:
    kind: str
    value: float
    unit: str | None
    rationale: str

    @classmethod
    def from_json(cls, raw: Mapping[str, Any], *, where: str, reference_unit: str) -> "Tolerance":
        tolerance = cls(kind=raw["kind"], value=float(raw["value"]), unit=raw.get("unit"), rationale=raw["rationale"])
        if tolerance.unit is not None:
            try:
                check_convertible(tolerance.unit, reference_unit)
            except QuantityError as exc:
                raise QuantityComparisonError(f"{where}: tolerance unit {tolerance.unit!r}: {exc}") from exc
        return tolerance

    def bound(self, left: float, right: float, unit: str) -> float:
        if self.kind == "absolute":
            return convert(self.value, self.unit, unit)
        return self.value * max(abs(left), abs(right))

    def to_json(self) -> dict[str, Any]:
        payload = {"kind": self.kind, "value": self.value, "rationale": self.rationale}
        if self.unit is not None:
            payload["unit"] = self.unit
        return payload


def compare_pair(left: Quantity, right: Quantity, *, unit: str, tolerance: Tolerance) -> tuple[str, float | None, float | None]:
    """``(status, difference, bound)``, both numbers in ``unit``."""
    a, b = converted(left, unit), converted(right, unit)
    if "not_evaluated" in (a.status, b.status):
        return "not_evaluated", None, None
    if a.status == b.status == "not_reached":
        return "both_not_reached", None, None
    if "not_reached" in (a.status, b.status):
        return "reached_on_one_side", None, None
    difference = abs(a.value - b.value)
    bound = tolerance.bound(a.value, b.value, unit)
    return ("within_tolerance" if difference <= bound else "outside_tolerance"), difference, bound


def overall_status(statuses: Iterable[str]) -> str:
    statuses = tuple(statuses)
    if any(status in _FAILING for status in statuses):
        return "failed"
    if "not_evaluated" in statuses:
        return "unavailable"
    return "passed"


@dataclass(frozen=True)
class _Pair:
    reference_label: str
    left_run: str
    left_quantity: str
    right_run: str
    right_quantity: str
    tolerance: Tolerance
    note: str | None


@dataclass(frozen=True)
class _Run:
    name: str
    plugin: str
    stack: tuple[str, ...]
    sweep_output: Path
    case: CaseRecord
    artifact: DataArtifact
    reader: Any | None
    points: Mapping[str, Point]
    max_offset: float | None
    evidence: dict[str, str] | None


def _resolve(base: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _location(base: Path, runs: Mapping[str, Any], side: Mapping[str, str]) -> tuple[str, str, str, str]:
    """What ``side`` actually names, independent of which run name it spells:
    the resolved sweep output, the case, the artifact and the quantity. Two
    sides that resolve identically compare a run against itself even when
    they name two different run keys (N1, controller review 2026-09-26)."""
    run = runs[side["run"]]
    return (str(_resolve(base, run["sweep_output"])), run["case_id"], run["artifact_id"], side["quantity"])


def _pairs(request: Mapping[str, Any], reference: PointReference, default: Tolerance, *, base: Path) -> tuple[_Pair, ...]:
    pairs = []
    runs = request["runs"]
    for index, raw in enumerate(request["pairs"]):
        label = raw["reference_label"]
        point = reference.points.get(label)
        if point is None:
            raise QuantityComparisonError(f"pair {index} names {label!r}; reference {reference.reference_id!r} has {sorted(reference.points)}")
        if point.coordinates is None:
            raise QuantityComparisonError(
                f"pair {index} names {label!r}, which reference {reference.reference_id!r} leaves unresolved: {point.unresolved}"
            )
        for side in ("left", "right"):
            if raw[side]["run"] not in runs:
                raise QuantityComparisonError(f"pair {index} {side} names run {raw[side]['run']!r}; the request has {sorted(runs)}")
        if _location(base, runs, raw["left"]) == _location(base, runs, raw["right"]):
            raise QuantityComparisonError(
                f"pair {index} compares {raw['left']} with itself: both resolve to the same "
                "(sweep_output, case_id, artifact_id, quantity), whatever the run names"
            )
        tolerance = default if "tolerance" not in raw else Tolerance.from_json(
            raw["tolerance"], where=f"pair {index}", reference_unit=reference.quantity_unit)
        pairs.append(_Pair(label, raw["left"]["run"], raw["left"]["quantity"], raw["right"]["run"],
                           raw["right"]["quantity"], tolerance, raw.get("note")))
    return tuple(pairs)


def _artifact(name: str, document: Mapping[str, Any], artifact_id: str) -> DataArtifact:
    declared = [raw for raw in document.get("expectedArtifacts", ()) if isinstance(raw, dict)]
    for raw in declared:
        if raw.get("artifact_id") == artifact_id:
            artifact = data_artifact_from_json(raw)
            if "{" in artifact.path_pattern:
                raise QuantityComparisonError(
                    f"run {name!r}: artifact {artifact_id!r} has the pattern {artifact.path_pattern!r}; a quantity is read from one literal path"
                )
            return artifact
    raise QuantityComparisonError(
        f"run {name!r}: the run declares no artifact {artifact_id!r}; it declares {[raw.get('artifact_id') for raw in declared]}"
    )


def _points(name: str, raw: Mapping[str, Any], reader: Any, names: tuple[str, ...]) -> tuple[Mapping[str, Point], float | None]:
    supplied = raw.get("points")
    if not reader.takes_points:
        if supplied is not None or raw.get("max_sampling_offset") is not None:
            raise QuantityComparisonError(
                f"run {name!r}: this artifact's reader ({reader.sampling_rule!r}) samples where the solver chose, so it takes no points; remove 'points' and 'max_sampling_offset'"
            )
        return {}, None
    if supplied is None:
        raise QuantityComparisonError(f"run {name!r}: this artifact's reader samples at supplied points; give 'points' for {list(names)}")
    if set(supplied["at"]) != set(names):
        raise QuantityComparisonError(f"run {name!r}: points are given for {sorted(supplied['at'])}, but its pairs use {sorted(names)}")
    try:
        points = {label: tuple(convert(float(v), supplied["unit"], reader.coordinate_unit) for v in xyz)
                  for label, xyz in supplied["at"].items()}
        offset = raw.get("max_sampling_offset")
        max_offset = None if offset is None else convert(float(offset), supplied["unit"], reader.coordinate_unit)
    except QuantityError as exc:
        raise QuantityComparisonError(f"run {name!r}: {exc}") from exc
    return points, max_offset


def _run_evidence(case: CaseRecord) -> dict[str, str] | None:
    state = _json_object(Path(case.workflow_state_path))
    snapshot = state.get("resume_snapshot")
    digest = state.get("workflow_digest")
    aggregate = snapshot.get("aggregate_digest") if isinstance(snapshot, Mapping) else None
    if not isinstance(digest, str) or not isinstance(aggregate, str):
        return None
    return {"case_id": case.case_id, "workflow_digest": digest, "input_provenance_digest": aggregate}


def _resolve_run(name: str, raw: Mapping[str, Any], *, base: Path, reference_unit: str, names: tuple[str, ...]) -> _Run:
    sweep_output = _resolve(base, raw["sweep_output"])
    try:
        context = build_sweep_context(sweep_output)
    except (OSError, ValueError, KeyError) as exc:
        raise QuantityComparisonError(f"run {name!r}: {sweep_output} is not a readable sweep output: {exc}") from exc
    case = next((c for c in context.cases if c.case_id == raw["case_id"]), None)
    if case is None:
        raise QuantityComparisonError(
            f"run {name!r}: sweep {sweep_output} has no case {raw['case_id']!r}; it has {sorted(c.case_id for c in context.cases)}"
        )
    document = _json_object(_resolve(sweep_output, case.run_document_path or ""))
    if not document:
        raise QuantityComparisonError(f"run {name!r}: case {case.case_id!r} has no readable run document")
    try:
        ctx = load_plugin_context(raw["plugin"])
    except Exception as exc:  # a plugin that does not load is refused by name
        raise QuantityComparisonError(f"run {name!r}: plugin {raw['plugin']!r} does not load: {type(exc).__name__}: {exc}") from exc
    stack = tuple(p["id"] for p in ctx.identity.to_json()["providers"])
    # One source of truth for this comparison: see
    # `provider_identity.stack_identity_mismatch`'s docstring for what is
    # compared and why (also called from `cli.py` and `run_document_exec.py`).
    mismatched = stack_identity_mismatch(document.get("plugin") or {}, ctx.identity.to_json())
    if mismatched:
        raise QuantityComparisonError(
            f"run {name!r}: plugin {raw['plugin']!r} loads a stack whose {', '.join(mismatched)} differ from what "
            f"case {case.case_id!r} was planned with"
        )
    artifact = _artifact(name, document, raw["artifact_id"])
    reader = ctx.capabilities.runtime_evidence.artifact_value_reader(artifact.format)
    points: Mapping[str, Point] = {}
    max_offset = None
    if reader is None:
        if raw.get("points") is not None or raw.get("max_sampling_offset") is not None:
            raise QuantityComparisonError(
                f"run {name!r}: the stack has no reader for format {artifact.format!r} (artifact {raw['artifact_id']!r}); "
                "'points'/'max_sampling_offset' cannot be checked against a reader that does not exist, so they are "
                "refused rather than silently ignored"
            )
    else:
        try:
            check_reader(reader, artifact_format=artifact.format)
            check_convertible(reader.value_unit, reference_unit)
        except QuantityError as exc:
            raise QuantityComparisonError(f"run {name!r}: {exc}") from exc
        points, max_offset = _points(name, raw, reader, names)
    return _Run(name, raw["plugin"], stack, sweep_output, case, artifact, reader, points, max_offset, _run_evidence(case))


def _quantities(run: _Run, names: tuple[str, ...]) -> dict[str, Quantity]:
    source = run.artifact.path_pattern

    def gap(reason: str) -> dict[str, Quantity]:
        return {q.name: q for q in not_evaluated(names, source_artifact=source, reason=reason)}

    if run.case.status != "completed":
        return gap(f"case {run.case.case_id!r} did not complete (status {run.case.status!r})")
    if run.reader is None:
        return gap(f"the stack has no reader for format {run.artifact.format!r} (artifact {run.artifact.artifact_id!r})")
    if run.case.case_root is None:
        return gap(f"the run document of case {run.case.case_id!r} records no caseRoot")
    case_root = _resolve(run.sweep_output, run.case.case_root)
    entry = reconcile_artifacts(case_root, (run.artifact,), case_id=run.case.case_id).artifacts[0]
    if entry["status"] != "matched":
        return gap(f"artifact {run.artifact.artifact_id!r} ({source}) is missing under {case_root}")
    try:
        read = read_quantities(run.reader, case_root, run.artifact, ReadRequest(names=names, points=run.points))
    except Exception as exc:  # any reader exception, not only ValueError, becomes a named gap; a report is always written
        return gap(f"the reader raised {type(exc).__name__}: {exc}")
    return {q.name: q for q in read}


def _side(run: _Run, quantity: Quantity, unit: str) -> dict[str, Any]:
    shown = converted(quantity, unit)
    requested = run.points.get(quantity.name)
    offset = math.dist(requested, quantity.sampled_at) if requested is not None and quantity.sampled_at is not None else None
    return {
        "run": run.name, "quantity": quantity.name, "status": shown.status, "value": shown.value,
        "unit": shown.unit, "declared_unit": quantity.unit, "sampling_rule": quantity.sampling_rule,
        "sampled_at": list(quantity.sampled_at) if quantity.sampled_at is not None else None,
        "sampled_at_unit": quantity.sampled_at_unit,
        "requested_at": list(requested) if requested is not None else None,
        "sampling_offset": offset, "source_artifact": quantity.source_artifact, "reason": quantity.reason,
    }


def _metric(pair: _Pair, runs: Mapping[str, _Run], quantities: Mapping[str, Mapping[str, Quantity]],
            reference: PointReference) -> dict[str, Any]:
    unit = reference.quantity_unit
    left_run, right_run = runs[pair.left_run], runs[pair.right_run]
    left_q, right_q = quantities[pair.left_run][pair.left_quantity], quantities[pair.right_run][pair.right_quantity]
    status, difference, bound = compare_pair(left_q, right_q, unit=unit, tolerance=pair.tolerance)
    left, right = _side(left_run, left_q, unit), _side(right_run, right_q, unit)
    if any(run.max_offset is not None and side["sampling_offset"] is not None and side["sampling_offset"] > run.max_offset
           for run, side in ((left_run, left), (right_run, right))):
        status = "sampled_off_point"  # location is checked before value
    return {
        "reference_label": pair.reference_label,
        "reference_coordinates": list(reference.points[pair.reference_label].coordinates),
        "reference_length_unit": reference.length_unit, "status": status, "unit": unit,
        "difference": difference, "bound": bound, "tolerance": pair.tolerance.to_json(),
        "left": left, "right": right, "note": pair.note,
    }


def _run_json(run: _Run) -> dict[str, Any]:
    reader = run.reader
    return {
        "plugin": run.plugin, "stack": list(run.stack), "sweep_output": str(run.sweep_output),
        "case_id": run.case.case_id, "execution_status": run.case.status,
        "artifact_id": run.artifact.artifact_id, "artifact_path": run.artifact.path_pattern,
        "artifact_format": run.artifact.format, "max_sampling_offset": run.max_offset,
        "reader": None if reader is None else {
            "value_unit": reader.value_unit, "sampling_rule": reader.sampling_rule,
            "coordinate_unit": reader.coordinate_unit, "takes_points": reader.takes_points,
            "sentinels": sorted(reader.sentinels),
        },
    }


def _write_once(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    try:
        os.link(temporary, path)
    except FileExistsError:
        raise QuantityComparisonError(
            f"report {path} already exists; a report is written once, and a changed request is a new report"
        ) from None
    except OSError as exc:
        # E.g. no hard-link support on this filesystem. Named, not a
        # traceback; `path` was never touched, so nothing is overwritten.
        raise QuantityComparisonError(f"cannot write report {path}: hard-linking it failed: {exc}") from exc
    finally:
        temporary.unlink()


def run_quantity_comparison(request_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    """Read, compare and report, once. Raises ``QuantityComparisonError``,
    naming why, for anything refused before the report is written."""
    request_path, report_path = Path(request_path), Path(report_path)
    if report_path.exists():
        raise QuantityComparisonError(
            f"report {report_path} already exists; a report is written once, and a changed request is a new report"
        )
    try:
        raw_bytes = request_path.read_bytes()
        request = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise QuantityComparisonError(f"cannot read the comparison request {request_path}: {exc}") from exc
    errors = schema_errors(request, _REQUEST_SCHEMA)
    if errors:
        raise QuantityComparisonError(f"{request_path} is not a comparison request: " + "; ".join(errors))
    base = request_path.parent
    try:
        reference = load_point_reference(_resolve(base, request["reference"]))
    except QuantityError as exc:
        raise QuantityComparisonError(str(exc)) from exc
    default = Tolerance.from_json(request["tolerance"], where="the request", reference_unit=reference.quantity_unit)
    pairs = _pairs(request, reference, default, base=base)
    names_by_run: dict[str, list[str]] = {}
    for pair in pairs:
        for run_name, quantity in ((pair.left_run, pair.left_quantity), (pair.right_run, pair.right_quantity)):
            names = names_by_run.setdefault(run_name, [])
            if quantity not in names:
                names.append(quantity)
    unused = sorted(set(request["runs"]) - set(names_by_run))
    if unused:
        raise QuantityComparisonError(f"run {unused[0]!r} is named but no pair uses it")
    runs = {
        name: _resolve_run(name, raw, base=base, reference_unit=reference.quantity_unit, names=tuple(names_by_run[name]))
        for name, raw in request["runs"].items()
    }
    # Nothing above read an artifact; everything below does.
    quantities = {name: _quantities(run, tuple(names_by_run[name])) for name, run in runs.items()}
    metrics = [_metric(pair, runs, quantities, reference) for pair in pairs]
    report = {
        "schema_version": 1,
        "status": overall_status(metric["status"] for metric in metrics),
        "checker": {"id": CHECKER_ID, "version": CHECKER_VERSION},
        "reference": {"id": reference.reference_id, "version": reference.version, "path": reference.path,
                      "digest": reference.digest, "quantity": reference.quantity_name, "unit": reference.quantity_unit},
        "request": {"path": str(request_path), "digest": "sha256:" + hashlib.sha256(raw_bytes).hexdigest()},
        "run_evidence": _deduplicated_run_evidence(runs.values()),
        "runs": {name: _run_json(run) for name, run in runs.items()},
        "metrics": metrics,
    }
    _write_once(report_path, report)
    return report


def _deduplicated_run_evidence(runs: Iterable[_Run]) -> list[dict[str, str]]:
    """One entry per distinct case, even when two run *names* in the request
    resolve to the same case (B2, controller review 2026-09-26): duplicate
    identical entries would make ``experiments._association_status``'s
    "exactly one match" check see more than one and report ``unverified``
    for a genuinely verified case."""
    seen: set[tuple[str, str, str]] = set()
    evidence: list[dict[str, str]] = []
    for run in runs:
        if run.evidence is None:
            continue
        key = (run.evidence["case_id"], run.evidence["workflow_digest"], run.evidence["input_provenance_digest"])
        if key in seen:
            continue
        seen.add(key)
        evidence.append(run.evidence)
    return evidence


def experiment_comparisons(report_path: str | Path, *, sweep_output: str | Path) -> tuple[ComparisonRequest, ...]:
    """The requests that attach one written report to every case it compared
    in one sweep (``experiments.inspect_sweep_experiment(..., comparisons=)``)."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text())
    target = Path(sweep_output).resolve()
    by_case: dict[str, ComparisonRequest] = {}
    for run in report["runs"].values():
        if Path(run["sweep_output"]).resolve() == target:
            by_case[run["case_id"]] = ComparisonRequest(
                case_id=run["case_id"], checker_id=report["checker"]["id"], checker_version=report["checker"]["version"],
                reference_id=report["reference"]["id"], reference_version=report["reference"]["version"],
                report_path=str(report_path),
            )
    return tuple(by_case.values())
