"""End-to-end CLI coverage: `plan --strict --entry <record>` must work end to end, and the run document it produces must advertise a `run --run-document <path>` command that itself works."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from plugins.toy import write_quantity_toy_case


def _native_toy_case(tmp_path: Path) -> Path:
    native = tmp_path / "native" / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"}))
    return native.parent


def test_plan_strict_over_a_tutorial_record_advertises_a_working_run_document_command(
    tmp_path, capsys,
):
    cases_root = _native_toy_case(tmp_path)

    exit_code = main([
        "plan", "--strict",
        "--plugin", "plugins.toy:ToyStack",
        "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])
    assert exit_code == 0, capsys.readouterr().out
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"

    command = payload["launch"]["command"]
    assert "--run-document" in command, command
    assert "--strict" not in command
    assert "--entry" not in command

    run_document_path = Path(command[command.index("--run-document") + 1])
    assert run_document_path.is_file(), (
        "the advertised run document must already be written to disk by "
        "`plan --strict` itself -- a record's case is committed at plan "
        "time, so the command it advertises must be immediately runnable"
    )
    run_document = json.loads(run_document_path.read_text())
    assert run_document["name"] == "toyTutorial"
    assert run_document["workflowDag"]["steps"][0]["command"] == "touch"
    assert run_document["workflowDag"]["steps"][0]["args"] == ["solved.marker"]
    case_root = Path(run_document["launch"]["caseRoot"])
    assert json.loads((case_root / "constant" / "mesh.json").read_text())["cells"] == "1"

    # The advertised command itself: `[sys.executable, "-m", "omnidriver",
    # "run", "--plugin", <selector>, "--run-document", <path>]` -- run it
    # in-process by dropping the interpreter/module-invocation prefix.
    assert command[:3] == [command[0], "-m", "omnidriver"]
    exit_code = main(command[3:])
    assert exit_code == 0, capsys.readouterr().out
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["status"] == "ok", run_payload
    assert run_payload["workflow_state"]["status"] == "completed"
    assert (case_root / "solved.marker").exists()


def test_run_strict_entry_over_a_tutorial_record_also_works_end_to_end(tmp_path, capsys):
    """`step`/`run --entry <record>` work through the same shared function `plan --strict` uses (`strict_planning.strict_plan`'s tutorial_record branch), rather than refusing by name."""
    cases_root = _native_toy_case(tmp_path)

    exit_code = main([
        "run", "--strict",
        "--plugin", "plugins.toy:ToyStack",
        "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])
    assert exit_code == 0, capsys.readouterr().out
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workflow_state"]["status"] == "completed"


def test_plan_strict_over_a_tutorial_record_whose_native_case_is_missing_refuses_with_structured_json(
    tmp_path, capsys,
):
    """`cli.main` turns a `TutorialRecordError` into the same structured JSON failure payload every comparable CLI refusal already produces (see e.g. `_context_from_run_document`'s `run_document_unreadable` payload) -- never a raw traceback."""
    empty_cases_root = tmp_path / "empty"
    empty_cases_root.mkdir()

    exit_code = main([
        "plan", "--strict",
        "--plugin", "plugins.toy:ToyStack",
        "--entry", "toyTutorial",
        "--cases-root", str(empty_cases_root),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "toyTutorial" in payload["error"]


def _one_case_sweep(tmp_path, cases_root):
    spec = tmp_path / "study.json"
    spec.write_text(json.dumps({
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {"mode": "zip", "independent": {"constant/mesh.json:cells": [7]}},
    }))
    return spec


@pytest.mark.parametrize("plugin", [
    "plugins.toy:RefusingRendererPlugin",
    "plugins.toy:RefusingResolverPlugin",
    "plugins.toy:RefusingReaderPlugin",
])
def test_a_renderer_resolver_or_reader_refusal_comes_back_as_the_cases_structured_error(tmp_path, capsys, plugin):
    """A refusal the plugin raises (a `ValueError` subclass, like openCARP's `ParFormatError`) while a case is committed -- from its case writer, or from the config-value reader reached through `split_unchanged` -- is that case's `materialization_error`, never a traceback."""
    from plugins.toy import TOY_REFUSAL

    cases_root = _native_toy_case(tmp_path)
    exit_code = main([
        "sweep-plan", "--plugin", plugin, "--spec", str(_one_case_sweep(tmp_path, cases_root)),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert exit_code == 1
    (case,) = json.loads(capsys.readouterr().out)["cases"]
    assert case["status"] == "failed"
    assert "constant/mesh.json" in case["materialization_error"]
    assert TOY_REFUSAL in case["materialization_error"]


def test_plan_strict_against_a_read_only_tree_without_a_scratch_dir_refuses_as_json_S_I3(
    tmp_path, capsys, monkeypatch,
):
    """With a scratch dir supplied, a read-only tutorials tree plans cleanly and is left untouched."""
    import os
    import stat

    cases_root = _native_toy_case(tmp_path)
    monkeypatch.delenv("OMNIDRIVER_SCRATCH_DIR", raising=False)
    before = sorted(p.relative_to(cases_root).as_posix() for p in cases_root.rglob("*"))
    argv = [
        "plan", "--strict", "--plugin", "plugins.toy:ToyStack",
        "--entry", "toyTutorial", "--cases-root", str(cases_root),
    ]
    cases_root.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        if os.access(cases_root, os.W_OK):
            pytest.fail("cannot make a read-only cases root here (running as root?); this test needs one")
        refused = main(argv)
        refusal = json.loads(capsys.readouterr().out)
        planned = main([*argv, "--scratch-dir", str(tmp_path / "scratch")])
        plan = json.loads(capsys.readouterr().out)
    finally:
        cases_root.chmod(stat.S_IRWXU)
    assert refused == 1
    assert refusal["status"] == "failed"
    assert "--scratch-dir" in refusal["error"]
    assert "OMNIDRIVER_SCRATCH_DIR" in refusal["error"]
    assert planned == 0, plan
    assert plan["status"] == "ok"
    after = sorted(p.relative_to(cases_root).as_posix() for p in cases_root.rglob("*"))
    assert after == before


def _write_spec(tmp_path: Path, spec: dict) -> Path:
    path = tmp_path / "sweep.json"
    path.write_text(json.dumps(spec))
    return path



@pytest.mark.parametrize("action", ["sweep-plan", "sweep-run"])
@pytest.mark.parametrize(("base_extra", "sweep", "fragment"), [
    # The whole-sweep refusal a record sweep without a cases root gets.
    ({}, {"mode": "zip", "independent": {"number_cells": [1, 2]}}, "must supply 'cases_root'"),
    # A study name the record does not resolve, refused up front for the sweep.
    ({"cases_root": None}, {"mode": "zip", "independent": {"no_such_axis": [1, 2]}}, "'no_such_axis'"),
    # A sweep-expansion refusal: a case id that is not path-safe.
    ({"cases_root": None}, {"mode": "zip", "independent": {
        "number_cells": [1, 2], "caseId": ["a/b", "c"],
    }}, "not path-safe"),
])
def test_a_record_sweep_refusal_is_the_clis_json_failure(
    tmp_path, capsys, action, base_extra, sweep, fragment,
):
    """A refusal of a record sweep as a whole must not escape `sweep-plan`/`sweep-run` as a Python traceback with nothing on stdout."""
    cases_root = _native_toy_case(tmp_path)
    base = {"entry": "toyTutorial"}
    for key, value in base_extra.items():
        base[key] = str(cases_root) if value is None else value
    spec = _write_spec(tmp_path, {"base": base, "sweep": sweep})

    exit_code = main([
        action, "--plugin", "plugins.toy:ToyStack",
        "--spec", str(spec), "--output-dir", str(tmp_path / "out"),
    ])
    captured = capsys.readouterr()
    assert exit_code == 1, captured.out
    payload = json.loads(captured.out)
    assert payload["status"] == "failed"
    assert payload["action"] == action
    assert payload["spec"] == str(spec)
    assert fragment in payload["error"], payload["error"]


def test_run_strict_entry_runs_a_record_whose_output_names_a_format(tmp_path, capsys):
    cases_root = tmp_path / "native"
    write_quantity_toy_case(cases_root, "a 1.5 0 0 0\n")

    exit_code = main([
        "run", "--strict", "--plugin", "plugins.toy:QuantityToyPlugin", "--entry", "toyQuantities",
        "--cases-root", str(cases_root), "--scratch-dir", str(tmp_path / "scratch"),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0, payload
    assert payload["workflow_state"]["status"] == "completed"
