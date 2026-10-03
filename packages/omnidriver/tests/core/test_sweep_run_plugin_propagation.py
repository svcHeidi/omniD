"""End to end and unmocked: a record-entry sweep's spawned ``omnidriver run --run-document`` child runs on the same plugin stack the parent was given via ``--plugin``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]


def _native_toy_case(tmp_path: Path) -> Path:
    native = tmp_path / "native" / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"}))
    return native.parent


def test_sweep_run_cli_propagates_the_plugin_to_its_spawned_children(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec = {
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {
            "mode": "cross_product",
            "independent": {"number_cells": [2, 3]},
            "dependent": [
                {"name": "caseId", "derive": "case_id_template", "of": ["number_cells"]},
            ],
        },
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(TESTS_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    result = subprocess.run(
        [
            sys.executable, "-m", "omnidriver", "sweep-run",
            "--plugin", "plugins.toy:ToyStack",
            "--spec", str(spec_path),
            "--output-dir", str(output_dir),
        ],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, (
        f"sweep-run failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert payload["case_count"] == 2, payload
    assert payload["completed_count"] == 2, payload
    assert payload["failed_count"] == 0, payload
    for case in payload["cases"]:
        assert case["status"] == "completed", case
