from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_remediation_record(
    output_dir: Path,
    *,
    step_id: str,
    attempt: int,
    applied_overrides: list[dict[str, Any]],
    resulting_status: str,
) -> None:
    """Append one audit line. Best-effort: never raises (must not crash a rerun)."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step_id": step_id,
        "attempt": attempt,
        "applied_overrides": applied_overrides,
        "resulting_status": resulting_status,
    }
    try:
        path = Path(output_dir) / "remediation_history.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return
