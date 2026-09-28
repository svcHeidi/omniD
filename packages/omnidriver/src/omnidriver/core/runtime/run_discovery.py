"""Discover past runs under a directory tree.

Yields one parsed ``workflow_state.json`` per run found, augmented with a
``_state_path`` key; malformed state files are silently skipped.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .workflow_orchestrator import STATE_FILENAME


def list_runs(root: Path) -> Iterator[dict]:
    """Yield every parseable `workflow_state.json` under `root`.

    Walks recursively. Order of iteration follows ``Path.rglob`` —
    filesystem-defined and not deterministic across platforms. Callers
    that need a stable order should sort by ``_state_path`` or
    ``started_at_utc``.
    """
    root = Path(root)
    if not root.is_dir():
        return
    for state_path in root.rglob(STATE_FILENAME):
        try:
            payload = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        payload["_state_path"] = str(state_path)
        yield payload
