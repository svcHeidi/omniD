"""``omnidriver check --studies DIR``: every sweep spec under a supplied folder, planned into scratch and reported."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from cli_refusal import refusal
from plugins.toy import TOY_PLUGIN, write_toy_native_case


def _studies(tmp_path: Path) -> Path:
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    studies = tmp_path / "studies"
    (studies / "cells").mkdir(parents=True)
    base = {"entry": "toyTutorial", "cases_root": str(cases_root)}
    (studies / "cells" / "sweep.json").write_text(json.dumps({
        "base": base, "sweep": {"mode": "cross_product", "independent": {"number_cells": [2, 3]}},
    }))
    (studies / "typo.json").write_text(json.dumps({
        "base": base, "sweep": {"mode": "zip", "independent": {
            "constant/mesh.json:cells": [4, 5], "constant/mesh.json:cell": [4, 5], "caseId": ["a", "b"],
        }},
    }))
    (studies / "unknown.json").write_text(json.dumps({
        "base": {**base, "entry": "noSuchRecord"}, "sweep": {"mode": "zip", "independent": {"number_cells": [2]}},
    }))
    (studies / "cells" / "results.json").write_text(json.dumps({"cells": [2, 3]}))
    (studies / "broken.json").write_text("{")
    return studies


def _check_studies(tmp_path: Path, capsys, studies: Path, *extra: str) -> tuple[int, dict]:
    code = main([
        "check", "--plugin", TOY_PLUGIN, "--studies", str(studies), "--scratch-dir", str(tmp_path / "scratch"), *extra,
    ])
    return code, json.loads(capsys.readouterr().out)


def test_every_study_is_planned_into_scratch_and_reported_and_the_exit_code_stays_zero(tmp_path, capsys):
    studies = _studies(tmp_path)
    native = tmp_path / "native"
    before = {p.as_posix(): p.read_bytes() for p in native.rglob("*") if p.is_file()}

    code, report = _check_studies(tmp_path, capsys, studies)

    assert code == 0, report
    by_study = {study["study"]: study for study in report["studies"]}
    assert sorted(by_study) == ["broken.json", "cells/sweep.json", "typo.json", "unknown.json"]

    cells = by_study["cells/sweep.json"]
    assert (cells["status"], cells["case_count"]) == ("ok", 2)
    assert [case["status"] for case in cells["cases"]] == ["ok", "ok"]
    staged = tmp_path / "scratch" / "studies" / "cells" / "sweep" / "cases"
    assert (staged / "case_0001" / "run_document.json").is_file() and (staged / "case_0002" / "run_document.json").is_file()

    typo = by_study["typo.json"]
    assert (typo["status"], typo["code"], typo["case_count"]) == ("failed", "cases_failed", 2)
    assert {case["status"] for case in typo["cases"]} == {"failed"}
    assert all(case["code"] and "constant/mesh.json:cell" in case["error"] for case in typo["cases"])

    assert by_study["unknown.json"]["status"] == "failed"
    assert by_study["unknown.json"]["code"] == "unknown_record"
    assert by_study["broken.json"]["code"] == "spec_unreadable"

    assert report["summary"] == {"studies": 4, "ok": 1, "blocked": 0, "failed": 3, "cases": 4, "cases_ok": 2}
    assert {p.as_posix(): p.read_bytes() for p in native.rglob("*") if p.is_file()} == before


def test_the_studies_folder_is_supplied_and_must_exist(tmp_path, capsys):
    code, report = _check_studies(tmp_path, capsys, tmp_path / "absent")
    assert code == 1 and "is not a directory" in report["error"]


def test_a_scratch_root_inside_the_studies_folder_is_refused(tmp_path, capsys):
    studies = _studies(tmp_path)
    code = main([
        "check", "--plugin", TOY_PLUGIN, "--studies", str(studies), "--scratch-dir", str(studies / "scratch"),
    ])
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and "inside the studies folder" in report["error"]


@pytest.mark.parametrize("argv", [
    ["check", "--studies", "s", "--record", "toyTutorial"],
    ["check", "--studies", "s", "--regression"],
    ["check", "--studies", "s", "--cases-root", "c"],
    ["plan", "--strict", "--entry", "toyTutorial", "--studies", "s"],
])
def test_studies_replace_the_conformance_checks_and_belong_to_check(argv, capsys):
    assert "--studies" in refusal(capsys, [*argv, "--plugin", TOY_PLUGIN])
