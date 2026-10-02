"""What the conformance checks share: a record's sweep through the CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SWEEP_TIMEOUT_S = 1800.0


def sweep_run(
    plugin: str, spec: Mapping[str, Any], *, work: Path, scratch_dir: Path,
    inputs: Mapping[str, str] | None = None, case_timeout_s: float | None = None,
    env: Mapping[str, str] | None = None, timeout_s: float = SWEEP_TIMEOUT_S,
) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
    """``omnidriver sweep-run`` of ``spec`` into ``work/out``, and its JSON payload (``None`` when it printed none)."""
    work.mkdir(parents=True, exist_ok=True)
    spec_path = work / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    argv = [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", plugin, "--spec", str(spec_path),
            "--output-dir", str(work / "out"), "--scratch-dir", str(scratch_dir)]
    if case_timeout_s is not None:
        argv += ["--case-timeout-s", str(case_timeout_s)]
    for name, path in (inputs or {}).items():
        argv += ["--input", f"{name}={path}"]
    proc = subprocess.run(argv, capture_output=True, text=True, env=None if env is None else dict(env), timeout=timeout_s)
    try:
        return proc, json.loads(proc.stdout)
    except ValueError:
        return proc, None


def sweep_spec(
    record: str, cases_root: Path, base: Mapping[str, Any], sweep: Mapping[str, Sequence[Any]],
) -> dict[str, Any]:
    return {
        "base": {"entry": record, "cases_root": str(cases_root), **base},
        "sweep": {"mode": "cross_product", "independent": {name: list(values) for name, values in sweep.items()}},
    }
