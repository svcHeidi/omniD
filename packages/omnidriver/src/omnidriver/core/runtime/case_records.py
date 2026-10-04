"""Solver-neutral durable records of a run: one case's record and a sweep's context.

Core records requests and execution state; it never inspects solver outputs."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .sweep_manifest import SWEEP_MANIFEST_FILENAME, CaseManifestEntry, read_manifest
from .workflow_orchestrator import STATE_FILENAME
from .workflow_runner import utc_now

#: The standalone case record's on-disk filename, named once here instead
#: of restated as a literal at each write site (``cli.py``,
#: ``sweep_runner.py``, ``runtime_records.CORE_RUNTIME_RECORDS``).
CASE_RECORD_FILENAME = "case_record.json"


@dataclass(frozen=True)
class CaseRecord:
    """One Core-owned execution record with opaque adapter-owned locations."""

    case_id: str
    resolved_axis_values: dict[str, Any]
    status: str
    outcome: str
    workflow_state_path: str
    case_output_dir: str | None
    setup_root: str | None
    case_root: str | None = None
    run_document_path: str | None = None
    override_hash: str | None = None
    started_at: str | None = None
    updated_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "resolved_axis_values": dict(self.resolved_axis_values),
            "status": self.status,
            "outcome": self.outcome,
            "workflow_state_path": self.workflow_state_path,
            "case_output_dir": self.case_output_dir,
            "setup_root": self.setup_root,
            "case_root": self.case_root,
            "run_document_path": self.run_document_path,
            "override_hash": self.override_hash,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


def write_case_record(path: Path, record: CaseRecord) -> None:
    """Persist a record atomically so readers never see a partial document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record.to_json(), indent=2))
    os.replace(temporary, path)


def _state_status(state_path: Path) -> str | None:
    """The status ``workflow_state.json`` records, or ``None`` when it is absent or unreadable."""
    try:
        status = json.loads(state_path.read_text()).get("status")
    except (OSError, ValueError, AttributeError):
        return None
    return status if isinstance(status, str) else None


def read_case_record(path: Path) -> CaseRecord | None:
    try:
        return CaseRecord(**json.loads(Path(path).read_text()))
    except (OSError, ValueError, TypeError):
        return None


def build_standalone_case_record(
    *, entry: str, case_root: Path, setup_root: Path | None, output_dir: Path,
) -> CaseRecord:
    """Record a run without scanning its output directory.

    A record already in ``output_dir`` (a sweep case's) keeps its identity and takes the run's status."""
    output_dir = Path(output_dir)
    workflow_state_path = output_dir / STATE_FILENAME
    status = _state_status(workflow_state_path) or "unknown"
    existing = read_case_record(output_dir / CASE_RECORD_FILENAME)
    if existing is not None:
        return replace(existing, status=status, updated_at=utc_now())
    return CaseRecord(
        case_id=entry, resolved_axis_values={}, status=status, outcome="fresh",
        workflow_state_path=str(workflow_state_path), case_output_dir=str(output_dir),
        setup_root=str(setup_root) if setup_root else None, case_root=str(case_root),
    )


def refresh_case_record(output_dir: Path) -> None:
    """Bring the status of the record in ``output_dir``, if there is one, up to its workflow state."""
    path = Path(output_dir) / CASE_RECORD_FILENAME
    existing = read_case_record(path)
    status = _state_status(Path(output_dir) / STATE_FILENAME)
    if existing is not None and status is not None:
        write_case_record(path, replace(existing, status=status, updated_at=utc_now()))


@dataclass(frozen=True)
class SweepContext:
    output_dir: str
    sweep_spec_hash: str
    started_at: str
    finished_at: str
    case_count: int
    completed_count: int
    failed_count: int
    cases: tuple[CaseRecord, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "sweep_spec_hash": self.sweep_spec_hash,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "case_count": self.case_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "cases": [case.to_json() for case in self.cases],
        }


def _run_document_field(raw_path: str, field: str, *, output_dir: Path) -> str | None:
    path = output_dir / raw_path
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    value = payload.get("launch", {}).get(field)
    return str(value) if value else None


def sweep_case_record(entry: CaseManifestEntry, output_dir: Path) -> CaseRecord:
    """A sweep case's record. Its status is the case's own ``workflow_state.json``, which a later ``step`` or
    ``run`` changes; the manifest's is what the sweep saw when it finished the case."""
    output_dir = Path(output_dir)
    candidate = Path(entry.workflow_state_path)
    state_path = candidate if candidate.is_absolute() else output_dir / candidate
    return CaseRecord(
        case_id=entry.case_id,
        resolved_axis_values=dict(entry.resolved_axis_values),
        status=_state_status(state_path) or entry.status,
        outcome=entry.outcome,
        workflow_state_path=str(state_path),
        case_output_dir=str(state_path.parent),
        setup_root=_run_document_field(entry.run_document_path, "setupRoot", output_dir=output_dir),
        case_root=_run_document_field(entry.run_document_path, "caseRoot", output_dir=output_dir),
        run_document_path=entry.run_document_path,
        override_hash=entry.override_hash,
        started_at=entry.started_at,
        updated_at=entry.updated_at,
    )


def build_sweep_context(output_dir: Path) -> SweepContext:
    """Read a sweep's durable Core records without inspecting solver outputs."""
    output_dir = Path(output_dir)
    manifest = read_manifest(output_dir / SWEEP_MANIFEST_FILENAME)
    records = tuple(sweep_case_record(entry, output_dir) for entry in manifest.cases)
    return SweepContext(
        output_dir=str(output_dir), sweep_spec_hash=manifest.sweep_spec_hash,
        started_at=manifest.created_at, finished_at=manifest.updated_at,
        case_count=len(records),
        completed_count=sum(record.status == "completed" for record in records),
        failed_count=sum(record.status == "failed" for record in records),
        cases=records,
    )
