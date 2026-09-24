"""M5, end to end and UNMOCKED: a record-entry sweep's spawned
``omnidriver run --run-document`` child must run on the SAME plugin stack
the parent CLI invocation was given via ``--plugin`` -- never falling back to
its own ``default_driver_context()``, which the parent's explicit selection
must never be silently replaced by (CLAUDE.md's "an explicitly-contexted
operation never falls back to the default").

This spawns a REAL ``python -m omnidriver sweep-run`` process, which itself
spawns REAL child ``python -m omnidriver run --run-document`` processes (no
``subprocess.run`` mock anywhere in this file) -- the other tests in
``test_sweep_runner.py`` mock the child process because they assert on
in-process details (which run-document path the sweep itself built); this
test instead proves the real, unmocked round trip end to end using the
existing zero-argument-constructible ``plugins.e2e_record_plugin
:E2ERecordPlugin`` fixture, over a 2-case record study.

**Un-skipped 2026-09-25 (consolidation).** It was skipped while the
``--plugin`` forwarding lived in a separate session. That work
(``DriverContext.plugin_selector``, recorded where a ``--plugin`` value
becomes a context) is now integrated, and every child command is built by
``core.runtime.run_command.omnidriver_run_command``, record sweeps included.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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
            "--plugin", "plugins.e2e_record_plugin:E2ERecordPlugin",
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
