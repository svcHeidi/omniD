"""``--case DIR``: a case folder that is not a record runs as an ad hoc record of one step, the stack's declared entrypoint."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from omnidriver.cli import main
from cli_refusal import refusal
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError, case_folder_record, lookup_record

from plugins.toy import E2EFolderPlugin, ToyStack

_DECLARED = "plugins.toy:E2EFolderPlugin"


def _case(root: Path, name: str = "myCase") -> Path:
    case = root / name
    (case / "system").mkdir(parents=True)
    (case / "system" / "input.txt").write_text("authored\n")
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\necho done > ran.marker\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return case


def test_a_folder_with_the_declared_entrypoint_is_a_one_step_record(tmp_path):
    ctx = driver_context(E2EFolderPlugin(), source="test:case-folder")
    record, cases_root = case_folder_record(_case(tmp_path), driver_context=ctx)
    assert (record.name, record.native_case_relpath, cases_root) == ("myCase", "myCase", tmp_path.resolve())
    assert record.axes == ()
    (step,) = record.workflow_steps
    assert (step.step_id, step.command) == ("run", ("run-test-case",))


def test_a_stack_that_declares_no_entrypoint_refuses_the_folder_by_name(tmp_path):
    ctx = driver_context(ToyStack(), source="test:case-folder")
    with pytest.raises(TutorialRecordError, match="declares none"):
        case_folder_record(_case(tmp_path), driver_context=ctx)


def test_a_folder_without_the_entrypoint_or_a_missing_folder_is_refused(tmp_path):
    ctx = driver_context(E2EFolderPlugin(), source="test:case-folder")
    bare = tmp_path / "bare"
    bare.mkdir()
    with pytest.raises(TutorialRecordError, match="no 'run-test-case' to run"):
        case_folder_record(bare, driver_context=ctx)
    with pytest.raises(TutorialRecordError, match="not a directory"):
        case_folder_record(tmp_path / "absent", driver_context=ctx)


def test_an_unknown_record_name_is_refused_with_the_registered_names_and_the_case_flag(tmp_path):
    ctx = driver_context(E2EFolderPlugin(), source="test:case-folder")
    with pytest.raises(TutorialRecordError, match=r"unknown tutorial record 'noSuch'.*--case"):
        lookup_record("noSuch", driver_context=ctx)


def test_plan_stages_the_folder_and_never_writes_it(tmp_path):
    ctx = driver_context(E2EFolderPlugin(), source="test:case-folder")
    case = _case(tmp_path / "cases")
    record, cases_root = case_folder_record(case, driver_context=ctx)
    before = sorted(p.name for p in case.rglob("*"))

    report = strict_plan(
        record, overrides={"cases_root": str(cases_root)}, scratch_root=tmp_path / "scratch",
        driver_context=ctx,
    )

    assert report.status == "ok", report.to_json()["workflow_diagnostics"]
    staged = Path(report.launch["case_root"])
    assert staged == (tmp_path / "scratch" / "records" / "myCase").resolve()
    assert (staged / "system" / "input.txt").read_text() == "authored\n"
    assert [step["command"] for step in report.workflow_dag["steps"]] == ["run-test-case"]
    assert sorted(p.name for p in case.rglob("*")) == before


def test_the_cli_runs_a_case_folder_through_the_declared_entrypoint(tmp_path, capsys, monkeypatch):
    tests_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(tests_root))
    case = _case(tmp_path / "cases")

    code = main([
        "run", "--strict", "--plugin", _DECLARED, "--case", str(case),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["status"] == "ok"
    staged = tmp_path / "scratch" / "records" / "myCase"
    assert (staged / "ran.marker").read_text() == "done\n"
    assert not (case / "ran.marker").exists()


@pytest.mark.parametrize("argv", [
    ["plan", "--strict", "--entry", "x", "--case", "dir"],
    ["plan", "--strict", "--case", "dir", "--cases-root", "elsewhere"],
    ["sweep-plan", "--case", "dir", "--spec", "sweep.json"],
    ["plan", "--strict"],
])
def test_case_is_exclusive_of_entry_and_cases_root_and_one_of_them_is_required(argv, capsys):
    refusal(capsys, [*argv, "--plugin", _DECLARED])


def test_the_cli_refuses_an_unknown_entry_as_json(tmp_path, capsys):
    code = main([
        "plan", "--strict", "--plugin", _DECLARED, "--entry", "noSuchRecord",
        "--cases-root", str(tmp_path), "--scratch-dir", str(tmp_path / "scratch"),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed" and "unknown tutorial record 'noSuchRecord'" in payload["error"]


def test_a_sweep_over_an_unknown_record_is_refused_as_json(tmp_path, capsys):
    spec = tmp_path / "sweep.json"
    spec.write_text(json.dumps({
        "base": {"entry": "noSuchRecord", "cases_root": str(tmp_path)},
        "sweep": {"mode": "cross_product", "independent": {"cells": [2]}},
    }))
    code = main(["sweep-plan", "--plugin", _DECLARED, "--spec", str(spec), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert "unknown tutorial record 'noSuchRecord'" in payload["error"]


def _repository_with_a_case_that_reaches_its_scripts(root: Path) -> Path:
    """cases/myCase/run-test-case runs ../../applications/scripts/helper, as a native cardiacCore ``Allrun`` does."""
    (root / "applications" / "scripts").mkdir(parents=True)
    helper = root / "applications" / "scripts" / "helper"
    helper.write_text("#!/bin/sh\necho done\n")
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    (root / "omnidriver.toml").write_text(
        f'plugin = "{_DECLARED}"\ntutorials = "cases"\nsource = "src"\nscripts = "applications/scripts"\n'
    )
    case = _case(root / "cases")
    (case / "run-test-case").write_text('#!/bin/sh\n"$(dirname "$0")/../../applications/scripts/helper" > ran.marker\n')
    return case


def _run_case(case: Path, repo: Path, scratch: Path, *extra: str) -> int:
    return main(["run", "--strict", "--repo", str(repo), "--case", str(case), "--scratch-dir", str(scratch), *extra])


def test_a_case_inside_the_repository_is_staged_at_its_depth_beside_the_repository_scripts(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    repo = tmp_path / "repo"
    case = _repository_with_a_case_that_reaches_its_scripts(repo)
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))

    assert _run_case(case, repo, tmp_path / "scratch") == 0, capsys.readouterr().out

    staging = tmp_path / "scratch" / "records" / "myCase"
    assert (staging / "cases" / "myCase" / "ran.marker").read_text() == "done\n"
    link = staging / "applications" / "scripts"
    assert link.is_symlink() and link.resolve() == (repo / "applications" / "scripts").resolve()
    assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")) == before


def test_the_guards_on_a_staged_case_hold_at_the_repository_depth(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    repo = tmp_path / "repo"
    case = _repository_with_a_case_that_reaches_its_scripts(repo)
    scratch = tmp_path / "scratch"
    assert _run_case(case, repo, scratch) == 0
    capsys.readouterr()

    assert _run_case(case, repo, scratch, "--fresh") == 1
    assert "--fresh" in capsys.readouterr().out

    assert _run_case(case, repo, repo / "cases" / "scratch") == 1
    assert "is inside cases root" in capsys.readouterr().out


def test_a_symlinked_staged_case_root_is_still_refused_at_the_repository_depth(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    repo = tmp_path / "repo"
    case = _repository_with_a_case_that_reaches_its_scripts(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    staged = tmp_path / "scratch" / "records" / "myCase" / "cases" / "myCase"
    staged.parent.mkdir(parents=True)
    staged.symlink_to(elsewhere, target_is_directory=True)

    assert _run_case(case, repo, tmp_path / "scratch") == 1
    assert "is a symlink" in capsys.readouterr().out
    assert list(elsewhere.iterdir()) == []


def test_a_case_outside_the_repository_is_staged_flat(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    repo = tmp_path / "repo"
    _repository_with_a_case_that_reaches_its_scripts(repo)
    outside = _case(tmp_path / "outside")

    assert _run_case(outside, repo, tmp_path / "scratch") == 0, capsys.readouterr().out
    assert (tmp_path / "scratch" / "records" / "myCase" / "ran.marker").is_file()
    assert not (tmp_path / "scratch" / "records" / "myCase" / "applications").exists()
