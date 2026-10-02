"""The scratch root is supplied, never invented (owner decision 2026-09-26)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.specs.paths import (
    SCRATCH_ENV_VAR,
    ScratchRootInsideCasesRoot,
    ScratchRootNotSupplied,
    resolve_scratch_root,
)
from omnidriver.core.tutorial_records import TutorialRecordError

RECORD_PLUGIN = "plugins.toy:ToyStack"


@pytest.fixture(autouse=True)
def _no_ambient_scratch(monkeypatch):
    # Every test here states its scratch explicitly; an inherited variable
    # would make the "nothing supplied" cases pass for the wrong reason.
    monkeypatch.delenv(SCRATCH_ENV_VAR, raising=False)


def _native_toy_case(tmp_path: Path) -> Path:
    native = tmp_path / "native" / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"}))
    return native.parent


def _tree(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


# --- the resolver -----------------------------------------------------------


def test_nothing_supplied_is_refused_by_name_saying_how_to_supply_one():
    with pytest.raises(ScratchRootNotSupplied) as caught:
        resolve_scratch_root(None)
    message = str(caught.value)
    assert "--scratch-dir" in message
    assert SCRATCH_ENV_VAR in message
    # The CLI already turns this family into structured JSON.
    assert isinstance(caught.value, TutorialRecordError)


def test_the_environment_variable_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setenv(SCRATCH_ENV_VAR, str(tmp_path / "from-env"))
    assert resolve_scratch_root(None) == tmp_path / "from-env"


def test_a_supplied_path_wins_over_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(SCRATCH_ENV_VAR, str(tmp_path / "from-env"))
    assert resolve_scratch_root(tmp_path / "supplied") == tmp_path / "supplied"


@pytest.mark.parametrize("inside", ["", "sub/scratch"])
def test_a_scratch_root_inside_the_cases_root_is_refused_naming_both(tmp_path, inside):
    cases_root = tmp_path / "cases"
    cases_root.mkdir()
    scratch = cases_root / inside if inside else cases_root
    with pytest.raises(ScratchRootInsideCasesRoot) as caught:
        resolve_scratch_root(scratch, cases_root=cases_root)
    assert str(scratch) in str(caught.value)
    assert str(cases_root) in str(caught.value)


def test_a_scratch_root_beside_the_cases_root_is_accepted(tmp_path):
    cases_root = tmp_path / "cases"
    assert resolve_scratch_root(tmp_path / "cases-scratch", cases_root=cases_root) == (
        tmp_path / "cases-scratch"
    )


# --- core: strict_plan over a record ---------------------------------------


def test_planning_a_record_with_no_scratch_is_refused_and_writes_nothing(tmp_path):
    from omnidriver.core.plugin_interface import load_plugin_context
    from omnidriver.core.strict_planning import strict_plan

    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    with pytest.raises(ScratchRootNotSupplied):
        strict_plan(
            "toyTutorial", overrides={"cases_root": str(cases_root)},
            driver_context=load_plugin_context(RECORD_PLUGIN),
        )
    assert _tree(cases_root) == before


def test_planning_a_record_stages_under_the_supplied_scratch_root(tmp_path):
    from omnidriver.core.plugin_interface import load_plugin_context
    from omnidriver.core.strict_planning import strict_plan

    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    scratch = tmp_path / "scratch"
    report = strict_plan(
        "toyTutorial", overrides={"cases_root": str(cases_root)},
        scratch_root=scratch, driver_context=load_plugin_context(RECORD_PLUGIN),
    )
    assert report.status == "ok"
    assert Path(report.launch["case_root"]).resolve().is_relative_to(scratch.resolve())
    assert (scratch / "records" / "toyTutorial").is_dir()
    assert _tree(cases_root) == before


def test_planning_a_record_honours_the_environment_variable(tmp_path, monkeypatch):
    from omnidriver.core.plugin_interface import load_plugin_context
    from omnidriver.core.strict_planning import strict_plan

    cases_root = _native_toy_case(tmp_path)
    monkeypatch.setenv(SCRATCH_ENV_VAR, str(tmp_path / "env-scratch"))
    report = strict_plan(
        "toyTutorial", overrides={"cases_root": str(cases_root)},
        driver_context=load_plugin_context(RECORD_PLUGIN),
    )
    assert report.status == "ok"
    assert (tmp_path / "env-scratch" / "records" / "toyTutorial").is_dir()


# --- the CLI: JSON refusals, never a traceback ------------------------------


@pytest.mark.parametrize("action", [["plan", "--strict"], ["run", "--strict"], ["step", "--strict", "--step", "solve"]])
def test_the_cli_refuses_an_unsupplied_scratch_root_as_json(tmp_path, capsys, action):
    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    exit_code = main([
        *action, "--plugin", RECORD_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "--scratch-dir" in payload["error"]
    assert SCRATCH_ENV_VAR in payload["error"]
    assert _tree(cases_root) == before


def test_the_cli_plans_under_a_supplied_scratch_dir(tmp_path, capsys):
    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    scratch = tmp_path / "scratch"
    exit_code = main([
        "plan", "--strict", "--plugin", RECORD_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(cases_root), "--scratch-dir", str(scratch),
    ])
    assert exit_code == 0, capsys.readouterr().out
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["launch"]["case_root"]).resolve().is_relative_to(scratch.resolve())
    assert _tree(cases_root) == before


def test_the_cli_refuses_a_scratch_dir_inside_the_cases_root_as_json(tmp_path, capsys):
    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    scratch = cases_root / "scratch"
    exit_code = main([
        "plan", "--strict", "--plugin", RECORD_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(cases_root), "--scratch-dir", str(scratch),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert str(scratch) in payload["error"] and str(cases_root) in payload["error"]
    assert _tree(cases_root) == before


def test_describe_needs_no_scratch_and_writes_nothing(tmp_path, capsys):
    """Lazy: describe previews in a discarded temporary directory, so it never asks for a scratch root and never refuses for want of one."""
    cases_root = _native_toy_case(tmp_path)
    before = _tree(cases_root)
    exit_code = main([
        "describe", "--plugin", RECORD_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
    ])
    assert exit_code == 0, capsys.readouterr().out
    assert json.loads(capsys.readouterr().out)["entry"]["entry_name"] == "toyTutorial"
    assert _tree(cases_root) == before


def _sweep_spec(tmp_path: Path, cases_root: Path) -> Path:
    spec = tmp_path / "study.json"
    spec.write_text(json.dumps({
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {"mode": "cross_product", "independent": {"constant/mesh.json:cells": ["2", "3"]}},
    }))
    return spec


@pytest.mark.parametrize("action", ["sweep-plan", "sweep-run"])
def test_a_sweep_with_no_output_dir_and_no_scratch_is_refused_as_json(tmp_path, capsys, action):
    cases_root = _native_toy_case(tmp_path)
    exit_code = main([action, "--plugin", RECORD_PLUGIN, "--spec", str(_sweep_spec(tmp_path, cases_root))])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "--scratch-dir" in payload["error"]


@pytest.mark.parametrize("action", ["sweep-plan", "sweep-run"])
def test_a_sweep_defaults_its_output_under_the_supplied_scratch_dir(tmp_path, action):
    from unittest import mock

    target = "omnidriver.cli.sweep_plan" if action == "sweep-plan" else "omnidriver.cli.sweep_run"
    result = {"case_count": 0, "cases": [], "completed_count": 0, "failed_count": 0}
    with mock.patch(target, return_value=result) as runner, mock.patch("builtins.print"):
        assert main([
            action, "--plugin", RECORD_PLUGIN, "--spec", "study.json",
            "--scratch-dir", str(tmp_path / "scratch"),
        ]) == 0
    assert Path(runner.call_args.kwargs["output_dir"]) == tmp_path / "scratch" / "sweeps" / "study"


def test_a_sweep_output_dir_wins_and_needs_no_scratch(tmp_path):
    from unittest import mock

    with mock.patch("omnidriver.cli.sweep_plan", return_value={"case_count": 0, "cases": []}) as runner, \
         mock.patch("builtins.print"):
        assert main([
            "sweep-plan", "--plugin", RECORD_PLUGIN, "--spec", "study.json",
            "--output-dir", str(tmp_path / "out"), "--scratch-dir", str(tmp_path / "scratch"),
        ]) == 0
        assert main([
            "sweep-plan", "--plugin", RECORD_PLUGIN, "--spec", "study.json",
            "--output-dir", str(tmp_path / "out"),
        ]) == 0
    assert [Path(c.kwargs["output_dir"]) for c in runner.call_args_list] == [tmp_path / "out"] * 2
