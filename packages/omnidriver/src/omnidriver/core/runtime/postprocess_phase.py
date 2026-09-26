"""Solver-neutral records for completed runs.

Core records requests and execution state. It does not inventory solver output
trees, infer execution from files, or expose arbitrary output content. An
adapter supplies declared result inspection when that is required.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .sweep_manifest import SWEEP_MANIFEST_FILENAME, read_manifest
from .workflow_orchestrator import STATE_FILENAME

#: The standalone case record's on-disk filename, named once here (final
#: review M6, 2026-09-26) instead of restated as a literal at each write
#: site (``cli.py``, ``sweep_runner.py``,
#: ``runtime_records.CORE_RUNTIME_RECORDS``).
CASE_RECORD_FILENAME = "case_record.json"


@dataclass(frozen=True)
class PostprocessOutcome:
    status: str
    message: str

    def to_json(self) -> dict[str, Any]:
        return {"status": self.status, "message": self.message}


def _not_configured() -> PostprocessOutcome:
    return PostprocessOutcome(
        status="not_configured",
        message="Core does not inspect solver outputs; select an adapter analysis capability.",
    )


def run_postprocess_phase(*, entry: str | None, output_dir: Path) -> PostprocessOutcome:
    """Report that no implicit Core output analysis is configured."""
    del entry, output_dir
    return _not_configured()


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


def build_standalone_case_record(
    *, entry: str, case_root: Path, setup_root: Path | None, output_dir: Path,
) -> CaseRecord:
    """Record a standalone run without scanning its output directory."""
    output_dir = Path(output_dir)
    workflow_state_path = output_dir / STATE_FILENAME
    status = "unknown"
    if workflow_state_path.is_file():
        try:
            status = json.loads(workflow_state_path.read_text()).get("status", "unknown")
        except json.JSONDecodeError:
            pass
    return CaseRecord(
        case_id=entry, resolved_axis_values={}, status=status, outcome="fresh",
        workflow_state_path=str(workflow_state_path), case_output_dir=str(output_dir),
        setup_root=str(setup_root) if setup_root else None, case_root=str(case_root),
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


def build_sweep_context(
    output_dir: Path,
    *,
    persist_case_records: bool = False,
) -> SweepContext:
    """Read a sweep's durable Core records without inspecting solver outputs.

    Inspection is read-only by default, including for archived results.  The
    sweep executor opts into persistence once it has finished updating its
    own manifest; a later reader must never rewrite that evidence.
    """
    output_dir = Path(output_dir)
    manifest = read_manifest(output_dir / SWEEP_MANIFEST_FILENAME)
    records: list[CaseRecord] = []
    for entry in manifest.cases:
        candidate = Path(entry.workflow_state_path)
        state_path = candidate if candidate.is_absolute() else output_dir / candidate
        record = CaseRecord(
            case_id=entry.case_id,
            resolved_axis_values=dict(entry.resolved_axis_values),
            status=entry.status,
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
        if persist_case_records and entry.case_record_path:
            write_case_record(output_dir / entry.case_record_path, record)
        records.append(record)
    return SweepContext(
        output_dir=str(output_dir), sweep_spec_hash=manifest.sweep_spec_hash,
        started_at=manifest.created_at, finished_at=manifest.updated_at,
        case_count=len(records),
        completed_count=sum(entry.status == "completed" for entry in manifest.cases),
        failed_count=sum(entry.status == "failed" for entry in manifest.cases),
        cases=tuple(records),
    )


def run_postprocessing_module(context: SweepContext, *, task: str) -> PostprocessOutcome:
    """Refuse an undeclared generic analysis task rather than guessing one."""
    del context, task
    return _not_configured()


def read_case_workflow_state(context: SweepContext, case_id: str) -> dict[str, Any]:
    """Read Core's durable execution state for one known case."""
    case = next((item for item in context.cases if item.case_id == case_id), None)
    if case is None:
        raise KeyError(f"unknown case_id {case_id!r}")
    state_path = Path(case.workflow_state_path)
    if not state_path.is_file():
        raise FileNotFoundError(
            f"workflow_state_path for case {case_id!r} no longer exists: {state_path}"
        )
    return json.loads(state_path.read_text())
