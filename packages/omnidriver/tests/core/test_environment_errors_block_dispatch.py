"""An environment-only error does not fail a plan, and it stops the run before anything executes."""
from __future__ import annotations

import json

from omnidriver.cli import main
from plugins.conformance_toy import FAILING_PREFLIGHT_PLUGIN, write_toy_native_case


def _run(tmp_path, capsys, action):
    write_toy_native_case(tmp_path / "native")
    args = [
        action, "--strict", "--plugin", FAILING_PREFLIGHT_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(tmp_path / "native"), "--scratch-dir", str(tmp_path / "scratch"),
    ]
    code = main(args)
    return code, json.loads(capsys.readouterr().out)


def test_the_plan_stays_ok_while_the_environment_stage_is_blocked(tmp_path, capsys):
    code, payload = _run(tmp_path, capsys, "plan")
    assert code == 0 and payload["status"] == "ok"
    assert payload["run_document"]["status"] == "planned"
    assert payload["run_document"]["validation"]["status"] == "ok"
    assert payload["readiness_score"]["status"] == "blocked"
    assert "environment_preflight" in payload["readiness_score"]["blocked_stages"]
    assert [item["code"] for item in payload["environment_diagnostics"]] == ["toy_environment_missing"]


def test_run_refuses_the_environment_error_before_executing(tmp_path, capsys):
    code, payload = _run(tmp_path, capsys, "run")
    assert code == 1 and payload["status"] == "failed"
    assert payload["error"] == "Execution environment preflight failed."
    assert [item["code"] for item in payload["environment_diagnostics"]] == ["toy_environment_missing"]
    assert not list((tmp_path / "scratch").rglob("solved.marker"))
