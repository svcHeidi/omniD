"""One table over a results folder: per task, adapter and condition."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(output: Path) -> list[dict]:
    """Group every ``task_record.json`` under ``output`` and reduce each group to one row."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for path in sorted(output.rglob("task_record.json")):
        record = json.loads(path.read_text())
        groups[(record["task"], record["adapter"], record["condition"])].append(record)
    rows = []
    for (task, adapter, condition), records in sorted(groups.items()):
        rows.append({
            "task": task, "adapter": adapter, "condition": condition, "trials": len(records),
            "successes": sum(r["success"] for r in records),
            "median_seconds": statistics.median(r["seconds"] for r in records),
            "median_turns": statistics.median(r["turns"] for r in records),
            "cost_usd": round(sum(r["cost_usd"] for r in records if r["cost_usd"] is not None), 4),
            "cost_unknown": sum(r["cost_usd"] is None for r in records),
            "timeouts": sum(r["timed_out"] for r in records),
            "oracle_errors": sum("oracle_error" in r["oracle"] for r in records),
            "harness_errors": sum(r["harness_error"] is not None for r in records),
            "mean_launches": statistics.mean(r["launches"] for r in records),
            "mean_refusals": statistics.mean(r["refusals"] for r in records),
            "tree_changed": sum(r.get("tree_before") != r.get("tree_after") for r in records),
        })
    return rows
