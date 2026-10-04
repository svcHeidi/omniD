"""``omnidriver check``: the conformance checks over a record's declared study, reported and never gating."""
from __future__ import annotations

import json

import pytest

from omnidriver.cli import main
from cli_refusal import refusal
from plugins.toy import PROBING_PLUGIN, TOY_PLUGIN, write_toy_native_case


def _check(tmp_path, capsys, *extra, prepare=None, plugin=TOY_PLUGIN):
    native = write_toy_native_case(tmp_path / "native")
    if prepare is not None:
        prepare(native)
    code = main([
        "check", "--plugin", plugin, "--cases-root", str(tmp_path / "native"),
        "--scratch-dir", str(tmp_path / "scratch"), *extra,
    ])
    return code, json.loads(capsys.readouterr().out)


def test_the_selected_checks_run_on_the_records_declared_study_and_are_reported(tmp_path, capsys):
    code, report = _check(tmp_path, capsys, "--record", "toyTutorial", "--checks", "C1,C3,C4")
    assert code == 0
    (record,) = report["records"]
    assert (record["record"], record["status"]) == ("toyTutorial", "passed")
    assert [(item["check"], item["passed"]) for item in record["checks"]] == [("C1", True), ("C3", True), ("C4", True)]
    assert report["summary"] == {"checks": 3, "passed": 3, "failed": 0}


def test_a_failing_check_is_reported_with_its_reason_and_the_exit_code_stays_zero(tmp_path, capsys):
    code, report = _check(
        tmp_path, capsys, "--checks", "C4",
        prepare=lambda native: (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"})),
    )
    (record,) = report["records"]
    assert code == 0 and record["status"] == "failed"
    assert report["summary"]["failed"] == 1 and record["checks"][0]["detail"]


def test_a_command_missing_from_the_shell_is_named_and_nothing_runs(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    code, report = _check(tmp_path, capsys, "--checks", "C1")
    (record,) = report["records"]
    assert (record["status"], record["missing_commands"]) == ("not_run", ["touch"])
    assert code == 0 and report["summary"]["checks"] == 0


def test_a_record_without_a_native_regression_script_is_reported(tmp_path, capsys):
    _code, report = _check(tmp_path, capsys, "--checks", "C1", "--regression")
    assert report["records"][0]["regression"]["status"] == "no_script"


def test_an_unknown_check_or_record_is_refused_by_name(tmp_path, capsys):
    code, report = _check(tmp_path, capsys, "--checks", "C99")
    assert code == 1 and "C99" in report["error"]
    code, report = _check(tmp_path / "again", capsys, "--record", "noSuchRecord")
    assert code == 1 and "noSuchRecord" in report["error"]


def test_check_needs_a_scratch_root_and_takes_no_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OMNIDRIVER_SCRATCH_DIR", raising=False)
    assert main(["check", "--plugin", TOY_PLUGIN, "--cases-root", str(tmp_path)]) == 1
    assert "scratch" in json.loads(capsys.readouterr().out)["error"].lower()
    assert "takes --plugin or --repo" in refusal(
        capsys, ["check", "--plugin", TOY_PLUGIN, "--scratch-dir", str(tmp_path / "s"), "--entry", "toyTutorial"],
    )


def test_a_probe_of_the_record_reports_beside_the_checks_and_a_drifted_one_fails_the_record(tmp_path, capsys):
    code, report = _check(tmp_path, capsys, "--record", "toyTutorial", "--checks", "C1", plugin=PROBING_PLUGIN)
    (record,) = report["records"]
    assert "probes" not in record, "a probe runs with the full set of checks, not a selection"

    code, report = _check(tmp_path / "all", capsys, "--record", "toyTutorial", plugin=PROBING_PLUGIN)
    (record,) = report["records"]
    probes = {name: (item["passed"], item["detail"]) for name, item in record["probes"].items()}
    assert code == 0 and probes == {
        "matches": (True, "3 models match"),
        "drifted": (False, "model A has a constant the solver lacks"),
        "unreadable": (False, "OSError: the utility is not built"),
    }
    assert all(item["passed"] for item in record["checks"]) and record["status"] == "failed"


def _native_with_script(tmp_path, body):
    native = tmp_path / "native" / "case"
    (native / "regression").mkdir(parents=True)
    (native / "regression" / "regressionTest.sh").write_text(body)
    return native, native / "regression" / "regressionTest.sh"


def test_the_native_regression_runs_in_a_copy_and_leaves_the_native_case_alone(tmp_path):
    from omnidriver.conformance.report import _regression

    native, script = _native_with_script(tmp_path, "echo ran > produced.txt; echo compared\n")
    result = _regression(script, native, tmp_path / "work", 30.0)
    assert (result["status"], result["exit_code"], result["script"]) == ("passed", 0, "regression/regressionTest.sh")
    assert "compared" in result["output_tail"]
    assert (tmp_path / "work" / "case" / "produced.txt").is_file()
    assert not (native / "produced.txt").exists()


@pytest.mark.parametrize(("body", "status"), [("exit 77\n", "skipped"), ("echo drifted >&2; exit 3\n", "failed")])
def test_a_regression_that_declines_or_fails_is_reported_as_such(tmp_path, body, status):
    from omnidriver.conformance.report import _regression

    native, script = _native_with_script(tmp_path, body)
    result = _regression(script, native, tmp_path / "work", 30.0)
    assert result["status"] == status
    assert "drifted" in result["output_tail"] or status == "skipped"


def test_a_regression_that_outlives_its_timeout_is_a_failure_naming_it(tmp_path):
    from omnidriver.conformance.report import _regression

    native, script = _native_with_script(tmp_path, "sleep 30\n")
    result = _regression(script, native, tmp_path / "work", 0.5)
    assert result["status"] == "failed" and "timed out" in result["detail"]


def test_the_regression_script_is_where_the_stacks_case_file_rule_puts_it(tmp_path):
    from types import SimpleNamespace

    from omnidriver.conformance.report import regression_script

    native, script = _native_with_script(tmp_path, "true\n")
    profile = SimpleNamespace(case_files=[
        SimpleNamespace(role="case.documentation", path="README.md"),
        SimpleNamespace(role="case.regression_test", path="regression/regressionTest.sh"),
    ])
    context = SimpleNamespace(stack=SimpleNamespace(call=lambda member: profile))
    assert regression_script(context, native) == script
    assert regression_script(context, tmp_path) is None
