from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CaseManifestEntry:
    case_id: str
    resolved_axis_values: dict[str, Any]
    override_hash: str
    run_document_path: str
    workflow_state_path: str
    status: str  # "pending" | "running" | "completed" | "failed"
    outcome: str  # "fresh" | "skipped" | "retried"
    started_at: str | None
    updated_at: str
    case_record_path: str = ""


@dataclass
class SweepManifest:
    schema_version: str
    sweep_spec_hash: str
    created_at: str
    updated_at: str
    cases: list[CaseManifestEntry] = field(default_factory=list)


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
    )
