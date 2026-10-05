from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


#: The sweep manifest's on-disk filename, named once here rather than
#: restated as a literal at each write/read site.
SWEEP_MANIFEST_FILENAME = "sweep_manifest.json"


@dataclass
class CaseManifestEntry:
    case_id: str
    resolved_axis_values: dict[str, Any]
    override_hash: str
    run_document_path: str
    workflow_state_path: str
    #: What the sweep observed of the case: ``running`` while it ran, then the status its workflow state had when
    #: the sweep finished with it, or ``stopped`` when a signal ended the sweep. The case's current status is its
    #: ``workflow_state.json``, which ``build_sweep_context`` reads.
    sweep_outcome: str  # "running" | "completed" | "failed" | "pending" | "stopped"
    outcome: str  # "fresh" | "skipped" | "retried"
    started_at: str | None
    updated_at: str
    case_record_path: str = ""
    #: A tutorial-record case's patches that already matched the case and
    #: were never written, each the same JSON shape
    #: `record_execution._serialize_sourced_patch` produces. Always `()`
    #: for a factory-entry case, which has no such concept.
    unchanged_patches: tuple[dict[str, Any], ...] = ()
    #: Why the case failed, when it did: the plan's or the child's ``error``,
    #: ``environment_diagnostics`` and ``failure_context``, as the case summary reports them.
    failure: dict[str, Any] = field(default_factory=dict)


@dataclass
class SweepManifest:
    schema_version: str
    sweep_spec_hash: str
    created_at: str
    updated_at: str
    cases: list[CaseManifestEntry] = field(default_factory=list)
    #: The study values every case shares, by source (the spec's ``base`` less its
    #: dispatch keys, and the CLI's own); a case's own values are its ``resolved_axis_values``.
    base_study: dict[str, Any] = field(default_factory=dict)
    cli_study: dict[str, Any] = field(default_factory=dict)


def _stable_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, default=str).encode("utf-8")


def compute_spec_hash(sweep_spec: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_stable_json_bytes(sweep_spec)).hexdigest()


def compute_override_hash(overrides: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_stable_json_bytes(overrides)).hexdigest()


def write_manifest(path: Path, manifest: SweepManifest) -> None:
    payload = asdict(manifest)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def read_manifest(path: Path) -> SweepManifest:
    payload = json.loads(path.read_text())
    cases = [CaseManifestEntry(**case) for case in payload["cases"]]
    return SweepManifest(
        schema_version=payload["schema_version"],
        sweep_spec_hash=payload["sweep_spec_hash"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        cases=cases,
        base_study=payload.get("base_study", {}),
        cli_study=payload.get("cli_study", {}),
    )
