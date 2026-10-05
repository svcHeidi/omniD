"""Solver-neutral durable records of a run: one case's record and a sweep's context.

Core records requests and execution state; it never inspects solver outputs."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .sweep_manifest import SWEEP_MANIFEST_FILENAME, CaseManifestEntry, read_manifest
from .workflow_orchestrator import STATE_FILENAME

#: The standalone case record's on-disk filename, named once here instead
#: of restated as a literal at each write site (``cli.py``,
#: ``sweep_runner.py``, ``runtime_records.CORE_RUNTIME_RECORDS``).
CASE_RECORD_FILENAME = "case_record.json"


@dataclass(frozen=True)
class CaseRecord:
    """What a case is, as ``case_record.json`` states it: identity and locations, never how the run went.

    Every location is relative to the folder holding the record. The case's
    status is its ``workflow_state.json``, the one place a run's progress is kept."""

    case_id: str
    resolved_axis_values: dict[str, Any]
    outcome: str
    workflow_state_path: str
    case_output_dir: str | None
    setup_root: str | None
    case_root: str | None = None
    run_document_path: str | None = None
    override_hash: str | None = None
    started_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "resolved_axis_values": dict(self.resolved_axis_values),
            "outcome": self.outcome,
            "workflow_state_path": self.workflow_state_path,
            "case_output_dir": self.case_output_dir,
            "setup_root": self.setup_root,
            "case_root": self.case_root,
            "run_document_path": self.run_document_path,
            "override_hash": self.override_hash,
            "started_at": self.started_at,
        }


@dataclass(frozen=True)
class SweepCase:
    """A case of a sweep as ``build_sweep_context`` reads it: its record's identity, with locations in the
    manifest's terms (the run document relative to the sweep's output directory, the others absolute) and
    the ``status`` its ``workflow_state.json`` has now, ``not_run`` when no workflow was started."""

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

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def write_case_record(path: Path, record: CaseRecord) -> None:
    """Persist a record atomically so readers never see a partial document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record.to_json(), indent=2))
    os.replace(temporary, path)


def workflow_status(state_path: Path) -> str | None:
    """The status ``workflow_state.json`` records, or ``None`` when it is absent or unreadable."""
    try:
        status = json.loads(Path(state_path).read_text()).get("status")
    except (OSError, ValueError, AttributeError):
        return None
    return status if isinstance(status, str) else None


def _relative_to(folder: Path, location: str | Path | None) -> str | None:
    return None if location is None else os.path.relpath(location, folder)


def build_standalone_case_record(
    *, entry: str, case_root: Path, setup_root: Path | None, output_dir: Path,
) -> CaseRecord:
    """Record a run by what it is, without scanning its output directory."""
    output_dir = Path(output_dir)
    return CaseRecord(
        case_id=entry, resolved_axis_values={}, outcome="fresh",
        workflow_state_path=STATE_FILENAME, case_output_dir=".",
        setup_root=_relative_to(output_dir, setup_root), case_root=_relative_to(output_dir, case_root),
    )


@dataclass(frozen=True)
class SweepContext:
    output_dir: str
    sweep_spec_hash: str
    started_at: str
    finished_at: str
    case_count: int
    completed_count: int
    failed_count: int
    cases: tuple[SweepCase, ...]

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


def sweep_case(entry: CaseManifestEntry, output_dir: Path) -> SweepCase:
    output_dir = Path(output_dir)
    candidate = Path(entry.workflow_state_path)
    state_path = candidate if candidate.is_absolute() else output_dir / candidate
    return SweepCase(
        case_id=entry.case_id,
        resolved_axis_values=dict(entry.resolved_axis_values),
        status=workflow_status(state_path) or "not_run",
        outcome=entry.outcome,
        workflow_state_path=str(state_path),
        case_output_dir=str(state_path.parent),
        setup_root=_run_document_field(entry.run_document_path, "setupRoot", output_dir=output_dir),
        case_root=_run_document_field(entry.run_document_path, "caseRoot", output_dir=output_dir),
        run_document_path=entry.run_document_path,
        override_hash=entry.override_hash,
        started_at=entry.started_at,
    )


def sweep_case_record(entry: CaseManifestEntry, output_dir: Path) -> CaseRecord:
    """The record of one sweep case, written into the case's own folder."""
    output_dir = Path(output_dir)
    case = sweep_case(entry, output_dir)
    folder = (output_dir / entry.case_record_path).parent
    return CaseRecord(
        case_id=case.case_id, resolved_axis_values=case.resolved_axis_values, outcome=case.outcome,
        workflow_state_path=_relative_to(folder, case.workflow_state_path),
        case_output_dir=_relative_to(folder, case.case_output_dir),
        setup_root=_relative_to(folder, case.setup_root), case_root=_relative_to(folder, case.case_root),
        run_document_path=_relative_to(folder, output_dir / entry.run_document_path),
        override_hash=case.override_hash, started_at=case.started_at,
    )


def build_sweep_context(output_dir: Path) -> SweepContext:
    """Read a sweep's durable Core records without inspecting solver outputs."""
    output_dir = Path(output_dir)
    manifest = read_manifest(output_dir / SWEEP_MANIFEST_FILENAME)
    cases = tuple(sweep_case(entry, output_dir) for entry in manifest.cases)
    return SweepContext(
        output_dir=str(output_dir), sweep_spec_hash=manifest.sweep_spec_hash,
        started_at=manifest.created_at, finished_at=manifest.updated_at,
        case_count=len(cases),
        completed_count=sum(case.status == "completed" for case in cases),
        failed_count=sum(case.status in {"failed", "not_run"} for case in cases),
        cases=cases,
    )
