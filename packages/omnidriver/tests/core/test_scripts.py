"""A solver repository's scripts: listed with a usage line, authorized and run as a workflow step."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.repository import Repository
from omnidriver.core.runtime.workflow import validate_workflow_commands
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.scripts import NO_USAGE, ScriptError, find_script, list_scripts, script_argv
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
    root = scripts.parent.resolve()
    repository = Repository(root=root, plugin=TOY_PLUGIN, tutorials=root, source=root, scripts=scripts.resolve())
    return dataclasses.replace(driver_context(ToyStack(), source="test:scripts"), repository=repository)


def test_every_script_is_listed_with_the_usage_line_its_file_states(context):
    listed = {item["name"]: item["usage"] for item in list_scripts(context)}
    assert listed == {
        "argparsed.py": NO_USAGE,
        "docstring.py": "Convert a thing.",
        "folder/tool.py": "Sums the numbers it is given.",
        "header.sh": "Sums the numbers it is given.",
        "silent.py": NO_USAGE,
        "usage.sh": "usage.sh <case> <step>",
    }


def test_listing_runs_no_script_however_it_mentions_help_or_option_parsing(scripts, context, tmp_path):
    marker = tmp_path / "ran"
    touch = f"open({str(marker)!r}, 'w').close()\n"
    (scripts / "silent.py").write_text(touch)
    (scripts / "argparsed.py").write_text("import argparse\n" + touch)
    (scripts / "mentions.sh").write_text(f"#!/bin/sh\n# pass --help to see more\ntouch {marker}\n")
    (scripts / "mentions.sh").chmod(0o755)
    list_scripts(context)
    assert not marker.exists()


def test_a_symlink_that_leaves_the_folder_is_neither_listed_nor_found(scripts, context, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text('"""Outside."""\n')
    (scripts / "linked.py").symlink_to(outside / "evil.py")
    (scripts / "linked_dir").symlink_to(outside, target_is_directory=True)
    (scripts / "inside_link.py").symlink_to(scripts / "docstring.py")
    names = {item["name"] for item in list_scripts(context)}
    assert "inside_link.py" in names
    assert not {"linked.py", "linked_dir/evil.py"} & names
    assert find_script("linked.py", context) is None and find_script("linked_dir/evil.py", context) is None


def test_nothing_is_listed_when_no_folder_is_supplied():
    assert list_scripts(driver_context(ToyStack(), source="test:scripts")) == []


@pytest.mark.parametrize("shadowed", ["run-test-case", "touch"])
def test_a_script_named_like_a_case_script_or_command_is_refused_not_preferred(scripts, context, shadowed):
    from plugins.toy import E2EFolderPlugin

    _executable(scripts / shadowed, "#!/bin/sh\n")
    stack = dataclasses.replace(driver_context(E2EFolderPlugin(), source="test:scripts"), repository=context.repository)
    [refusal] = validate_workflow_commands(_dag(shadowed, []), driver_context=stack)
    assert refusal.code == "ambiguous_workflow_command" and shadowed in refusal.message


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


def _script_repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    write_toy_native_case(repo / "tutorials")
    (repo / "applications" / "scripts").mkdir(parents=True)
    (repo / "applications" / "scripts" / "solve.py").write_text("open('solved.marker', 'w').close()\n")
    (repo / "omnidriver.toml").write_text(
        'plugin = "plugins.toy:ScriptStepToy"\ntutorials = "tutorials"\nsource = "src"\nscripts = "applications/scripts"\n'
    )
    return repo


def test_a_planned_script_step_runs_from_the_plans_own_launch_command(tmp_path, capsys):
    repo = _script_repository(tmp_path)
    assert main([
        "plan", "--strict", "--repo", str(repo), "--entry", "toyTutorial", "--scratch-dir", str(tmp_path / "scratch"),
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    launched = subprocess.run(plan["launch"]["command"], capture_output=True, text=True, timeout=120)
    assert json.loads(launched.stdout)["status"] == "ok", launched.stdout


def test_check_runs_a_script_step_in_the_repositorys_own_child_processes(tmp_path, capsys):
    repo = _script_repository(tmp_path)
    assert main([
        "check", "--repo", str(repo), "--scratch-dir", str(tmp_path / "scratch"), "--record", "toyTutorial",
        "--checks", "C6,C7",
    ]) == 0
    [entry] = json.loads(capsys.readouterr().out)["records"]
    assert [(v["check"], v["status"]) for v in entry["checks"]] == [("C6", "passed"), ("C7", "passed")], entry
