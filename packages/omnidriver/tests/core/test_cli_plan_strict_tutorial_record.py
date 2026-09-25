"""End-to-end CLI coverage for P1 (docs/superpowers/specs/2026-09-24-
tutorials-are-pointers-design.md, "Owner decisions" dated 2026-09-25):
`plan --strict --entry <record>` must work end to end, and the run
document it produces must advertise a `run --run-document <path>` command
that ITSELF works -- never the `run --strict --entry <record>` this used to
(uncatchably) refuse with, per `registry._materialize_resolved_entry`'s own
explicit refusal ("tutorial records are not yet runnable through
load_entry_spec").

Uses the zero-argument-constructible `plugins.e2e_record_plugin
:E2ERecordPlugin` fixture -- the same "core test plugin" already exercised
end to end for `sweep-run` by `test_sweep_run_plugin_propagation.py` -- via
`omnidriver.cli.main` in-process. `pythonpath = ["tests"]`
(packages/omnidriver/pyproject.toml) makes `plugins.*` importable here the
same way it does for every other CLI test in this directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.cli import main


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
        "--plugin", "plugins.e2e_record_plugin:E2ERecordPlugin",
        "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
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
    """P1's own explicit choice, decided and reported: `step`/`run --entry
    <record>` work through the SAME shared function `plan --strict` uses
    (`strict_planning.strict_plan`'s new tutorial_record branch), rather
    than refusing by name -- `_context_from_entry` calls `strict_plan`
    exactly the way it always has, and gained record support for free once
    `strict_plan` itself stopped refusing that resolution kind."""
    cases_root = _native_toy_case(tmp_path)

    exit_code = main([
        "run", "--strict",
        "--plugin", "plugins.e2e_record_plugin:E2ERecordPlugin",
        "--entry", "toyTutorial",
        "--cases-root", str(cases_root),
    ])
    assert exit_code == 0, capsys.readouterr().out
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workflow_state"]["status"] == "completed"


def test_plan_strict_over_a_tutorial_record_whose_native_case_is_missing_refuses_with_structured_json(
    tmp_path, capsys,
):
    """P1's `cli.main` fix: a `TutorialRecordError` becomes the same
    structured JSON failure payload every comparable CLI refusal already
    produces (see e.g. `_context_from_run_document`'s
    `run_document_unreadable` payload) -- never a raw traceback."""
    empty_cases_root = tmp_path / "empty"
    empty_cases_root.mkdir()

    exit_code = main([
        "plan", "--strict",
        "--plugin", "plugins.e2e_record_plugin:E2ERecordPlugin",
        "--entry", "toyTutorial",
        "--cases-root", str(empty_cases_root),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "toyTutorial" in payload["error"]


import pytest


@pytest.mark.parametrize("plugin", [
    "plugins.conformance_toy:RefusingRendererPlugin",
    "plugins.conformance_toy:RefusingResolverPlugin",
])
def test_a_renderer_or_resolver_refusal_comes_back_as_structured_json_I2(tmp_path, capsys, plugin):
    """Wave-2 review I2: a refusal the plugin's case writer raises (a
    ``ValueError`` subclass, like openCARP's ``ParFormatError``) used to escape
    ``plan --strict`` as a traceback with empty stdout, while a validator
    refusal came back as JSON. Both now take the same path."""
    from plugins.conformance_toy import TOY_REFUSAL

    cases_root = _native_toy_case(tmp_path)
    config = tmp_path / "study.json"
    config.write_text(json.dumps({"constant/mesh.json:cells": 7}))
    exit_code = main([
        "plan", "--strict", "--plugin", plugin, "--entry", "toyTutorial",
        "--cases-root", str(cases_root), "--config", str(config),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "constant/mesh.json" in payload["error"]
    assert TOY_REFUSAL in payload["error"]


@pytest.mark.parametrize("action", [["plan", "--strict"], ["describe"]])
def test_a_config_reader_refusal_comes_back_as_structured_json_naming_document_and_key_S_M1(
    tmp_path, capsys, action,
):
    """Final review S-M1: a refusal the config-value reader raises (openCARP's
    F1/F10 ``ParFormatError``) is a third refusal layer, reached through
    ``split_unchanged``. It escaped both ``plan --strict`` and ``describe`` as
    a traceback with empty stdout; it now comes back as JSON naming the
    document and key it was reading."""
    from plugins.conformance_toy import REFUSING_READER_PLUGIN, TOY_REFUSAL

    cases_root = _native_toy_case(tmp_path)
    config = tmp_path / "study.json"
    config.write_text(json.dumps({"constant/mesh.json:cells": 7}))
    exit_code = main([
        *action, "--plugin", REFUSING_READER_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(cases_root), "--config", str(config),
    ])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "constant/mesh.json:cells" in payload["error"]
    assert TOY_REFUSAL in payload["error"]
