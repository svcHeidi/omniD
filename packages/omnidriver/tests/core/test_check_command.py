"""``omnidriver check``: the conformance checks over a record's declared study, reported and never gating."""
from __future__ import annotations

import json

import pytest

from omnidriver.cli import main
from plugins.conformance_toy import TOY_PLUGIN, write_toy_native_case


def _check(tmp_path, capsys, *extra, prepare=None):
    native = write_toy_native_case(tmp_path / "native")
    if prepare is not None:
        prepare(native)
    code = main([
        "check", "--plugin", TOY_PLUGIN, "--cases-root", str(tmp_path / "native"),
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
    with pytest.raises(SystemExit):
        main(["check", "--plugin", TOY_PLUGIN, "--scratch-dir", str(tmp_path / "s"), "--entry", "toyTutorial"])
