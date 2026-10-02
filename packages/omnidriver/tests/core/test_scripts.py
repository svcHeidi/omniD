"""A solver repository's scripts: listed with a usage line, authorized and run as a workflow step."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.workflow import validate_workflow_commands
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.scripts import ScriptError, find_script, list_scripts, script_argv
from plugins.toy import TOY_PLUGIN, ToyStack, write_toy_native_case

SHEBANG_HEADER = "# Description\n#     Sums the numbers it is given.\n#\n#------\n"


def _executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def scripts(tmp_path) -> Path:
    root = tmp_path / "applications" / "scripts"
    root.mkdir(parents=True)
    (root / "docstring.py").write_text('"""Convert a thing.\n\nLong text."""\nprint("ran")\n')
    (root / "argparsed.py").write_text(
        "import argparse\nargparse.ArgumentParser(description='Parsed help line').parse_args()\n"
    )
    (root / "silent.py").write_text("print('would run')\n")
    _executable(root / "header.sh", "#!/bin/sh\n" + SHEBANG_HEADER + "echo done\n")
    _executable(root / "usage.sh", '#!/bin/sh\necho "usage: $0 <case> <step>" >&2\n')
    _executable(root / "folder" / "tool.py", "#!/usr/bin/env python3\n" + SHEBANG_HEADER)
    (root / "folder" / "library.py").write_text('"""Imported by tool.py."""\n')
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("")
    (root / "README.md").write_text("not a script")
    (root / ".hidden.py").write_text("")
    return root


@pytest.fixture
def context(scripts):
    """A stack whose repository keeps its scripts in ``scripts``."""
    return dataclasses.replace(driver_context(ToyStack(), source="test:scripts"), scripts_dir=scripts.resolve())


def test_every_script_is_listed_with_the_usage_line_its_file_states(context):
    listed = {item["name"]: item["usage"] for item in list_scripts(context, os.environ)}
    assert listed == {
        "argparsed.py": "usage: argparsed.py [-h]",
        "docstring.py": "Convert a thing.",
        "folder/tool.py": "Sums the numbers it is given.",
        "header.sh": "Sums the numbers it is given.",
        "silent.py": None,
        "usage.sh": "usage.sh <case> <step>",
    }


def test_a_script_that_states_no_usage_and_parses_no_options_is_never_executed(scripts, context, tmp_path):
    marker = tmp_path / "ran"
    (scripts / "silent.py").write_text(f"open({str(marker)!r}, 'w').close()\n")
    list_scripts(context, os.environ)
    assert not marker.exists()


def test_nothing_is_listed_when_no_folder_is_supplied():
    assert list_scripts(driver_context(ToyStack(), source="test:scripts"), os.environ) == []


@pytest.mark.parametrize("name", ["../outside.py", "/etc/passwd", "tests/test_x.py", "folder/library.py", "README.md", ".hidden.py", "missing.py"])
def test_only_a_listed_script_is_found(scripts, context, name):
    (scripts.parent / "outside.py").write_text("")
    assert find_script(name, context) is None


def test_a_py_script_runs_under_the_python_on_the_stacks_path(scripts, tmp_path):
    python = tmp_path / "bin" / "python3"
    _executable(python, "#!/bin/sh\n")
    assert script_argv(scripts / "docstring.py", {"PATH": str(python.parent)}) == (str(python), str(scripts / "docstring.py"))
    with pytest.raises(ScriptError, match="python3"):
        script_argv(scripts / "docstring.py", {"PATH": str(tmp_path / "nowhere")})
    assert script_argv(scripts / "header.sh", {}) == (str(scripts / "header.sh"),)


def _dag(command: str, args: list[str]) -> dict:
    return {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [{
            "id": "run", "command": command, "args": args, "cwd": ".", "depends_on": [], "produces": [],
            "consumes": [], "retry_policy": {"max_attempts": 1}, "command_display": command,
        }],
    }


def test_a_script_name_is_an_authorized_workflow_command_only_where_a_folder_is_supplied(context):
    assert validate_workflow_commands(_dag("docstring.py", []), driver_context=context) == ()
    assert validate_workflow_commands(_dag("folder/tool.py", []), driver_context=context) == ()
    for refused in ("../outside.py", "folder/library.py", "rm"):
        codes = {d.code for d in validate_workflow_commands(_dag(refused, []), driver_context=context)}
        assert codes == {"unknown_workflow_command"}, refused
    bare = driver_context(ToyStack(), source="test:scripts")
    codes = {d.code for d in validate_workflow_commands(_dag("docstring.py", []), driver_context=bare)}
    assert codes == {"unknown_workflow_command"}


def test_a_script_step_runs_with_the_interpreter_from_the_step_environment(scripts, context, tmp_path):
    if shutil.which("python3") is None:
        pytest.skip("no python3 on PATH")
    (scripts / "echo_args.py").write_text("import sys\nprint(sys.version_info.major, *sys.argv[1:])\n")
    dag = _dag("echo_args.py", ["--case", "."])
    case = tmp_path / "case"
    case.mkdir()
    result = run_workflow_step(
        dag, initial_workflow_state(dag), "run", case_root=case, log_dir=case / "logs", env=dict(os.environ),
        driver_context=context,
    )
    assert result.state.to_json()["status"] == "completed", Path(result.stderr_log).read_text()
    assert Path(result.stdout_log).read_text().strip() == "3 --case ."


def test_describe_lists_the_repositorys_scripts_beside_its_records(tmp_path, capsys):
    repo = tmp_path / "repo"
    write_toy_native_case(repo / "tutorials")
    scripts_dir = repo / "applications" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "convert.py").write_text('"""Convert it."""\n')
    (repo / "omnidriver.toml").write_text(
        f'plugin = "{TOY_PLUGIN}"\ntutorials = "tutorials"\n'
        'source = "src"\nscripts = "applications/scripts"\n'
    )
    assert main(["describe", "--entry", "toyTutorial", "--repo", str(repo)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"] and [(s["name"], s["usage"]) for s in payload["scripts"]] == [("convert.py", "Convert it.")]
