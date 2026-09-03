"""``sweep-plan`` must answer in its own contract, like ``plan --strict``.

A sweep already reports a per-case failure structurally -- ``status:
"failed"`` plus ``materialization_error`` on that case -- and keeps going.
That is the whole point of a sweep: one bad axis value should cost you one
case, not the command.

Two paths bypassed it. The per-case guard caught only ``OSError`` and
``ValueError``, so anything a tutorial factory raised (a ``KeyError`` for an
unknown ionic model, say) escaped and took the run down with a traceback --
zero bytes on stdout for the caller. And the spec file was read before any
guard at all, so a malformed JSON spec did the same.

Phase 2 Task M2: ``test_a_factory_failure_fails_one_case_not_the_command``
moved to packages/omnidriver-cardiacfoam/tests/test_sweep_plan_contract.py
-- it needs the real ``singleCell`` factory to prove one bad axis costs one
case, which is cardiacFoam-specific. The three tests kept here never depend
on that: the two malformed-spec tests never reach ``_SPEC``'s content at all
(spec loading fails before expansion), and the valid-spec test only checks
the absence of ``spec_error``, not what happened to any case. ``_SPEC`` was
trimmed to a trivially generic single-axis sweep and
``generic_openfoam_context()`` satisfies ``sweep_plan``'s now-mandatory
``driver_context`` -- no cardiac fixture data needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.runtime.sweep_runner import sweep_plan
from conftest import NO_REPO_ROOT, repo_root, skip_without_repo
from omnidriver.core.plugin_interface import generic_openfoam_context

_CTX = generic_openfoam_context()

_SPEC = {
    "base": {},
    "sweep": {
        "mode": "zip",
        "independent": {
            "axisA": ["valueA", "valueB"],
        },
    },
}


def test_a_malformed_spec_is_reported_structurally(tmp_path):
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text("{ not json")

    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    assert report["case_count"] == 0
    assert report["cases"] == []
    assert "spec_error" in report
    json.dumps(report)  # must be serialisable


def test_a_valid_spec_reports_no_spec_error(tmp_path):
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_SPEC))
    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)
    assert "spec_error" not in report


@skip_without_repo
def test_a_malformed_spec_still_exits_non_zero(tmp_path):
    """Structured is not the same as successful."""
    import subprocess
    import sys

    spec_path = tmp_path / "sweep.json"
    spec_path.write_text("{ not json")
    driver_root = repo_root or NO_REPO_ROOT

    result = subprocess.run(
        [
            sys.executable, "-m", "omnidriver", "sweep-plan",
            # --plugin none selects generic_openfoam_context() the same way
            # _CTX does above, so this subprocess doesn't need
            # omnidriver-cardiacfoam installed to reach the spec-loading
            # guard this test targets.
            "--plugin", "none",
            "--spec", str(spec_path), "--output-dir", str(tmp_path / "out"),
        ],
        cwd=driver_root, capture_output=True, text=True,
    )
    assert result.returncode != 0, result.stdout
    assert json.loads(result.stdout)["spec_error"]
