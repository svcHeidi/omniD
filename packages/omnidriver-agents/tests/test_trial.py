import json
import os
import re
import subprocess
import sys

import pytest

from omnidriver_agents import trial
from omnidriver_agents.task import Oracle, Task
from omnidriver_agents.trial import TrialSetup, _git, _refusals, run_trial

ORACLE = """import json, os, sys
answer = json.load(open(sys.argv[1] + "/answer.json"))
print(json.dumps({"status": "passed" if answer.get("P8") == 42 else "failed", "secret": os.environ.get("SECRET")}))
"""


def _task(tmp_path, argv=None):
    (tmp_path / "oracle.py").write_text(ORACLE)
    argv = argv or (sys.executable, str(tmp_path / "oracle.py"), "{trial}")
    return Task(id="t", role="runner", brief="go", programs=("solver",), tree=None, wall_seconds=60,
                oracle=Oracle(tuple(argv), "status", ("passed",)), digest="d" * 64)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    if repo.exists():
        return repo
    (repo / "agent-handbook").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("router")
    (repo / "agent-handbook/runner.md").write_text("runner")
    (repo / "agent-handbook/guidance-manifest.yaml").write_text(
        "version: 1\ncommon: [AGENTS.md]\nroles:\n  runner:\n    required: [agent-handbook/runner.md]\n")
    for args in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def _python(tmp_path, exit_code, name="python"):
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    path.chmod(0o755)
    return path


def _setup(tmp_path, condition, **over):
    omnid_bin = tmp_path / "venv-bin"
    omnid_bin.mkdir(exist_ok=True)
    (omnid_bin / "omnidriver").write_text("#!/bin/sh\necho '{\"status\": \"failed\", \"error\": \"x\"}'\n")
    (omnid_bin / "omnidriver").chmod(0o755)
    (omnid_bin / "pytest").write_text("#!/bin/sh\n")
    (omnid_bin / "pytest").chmod(0o755)
    fields = dict(output=tmp_path / "out", condition=condition, omnid_repo=_repo(tmp_path),
                  omnidriver_bin=omnid_bin / "omnidriver", agent_python=_python(tmp_path, 1),
                  agent_home=tmp_path / "home")
    return TrialSetup(**{**fields, **over})


def _folder(tmp_path):
    [folder] = (tmp_path / "out").iterdir()
    return folder


def test_omnid_gets_guidance_and_omnidriver_and_the_oracle_decides(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["omnidriver plan"], answer={"P8": 42},
                           init={"model": "m-1", "plugins": [], "mcp_servers": [], "hooks_seen": 0})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "omnid"), 0)
    assert "router" in adapter.calls[0]["system"]
    assert [p for p, _ in record["guidance"]] == ["AGENTS.md", "agent-handbook/runner.md"]
    assert record["refusals"] == 1 and record["success"] is True
    assert record["final_text"] == "done" and record["model_resolved"] == "m-1"
    assert record["isolation"] == {"plugins": [], "mcp_servers": [], "hooks_seen": 0}
    folder = _folder(tmp_path)
    assert json.loads((folder / "task_record.json").read_text()) == record
    assert (folder / "transcript.jsonl").exists()


def test_bare_gets_no_guidance_and_no_omnidriver(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["command -v omnidriver || echo absent"], answer={"P8": 1})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "bare"), 0)
    assert adapter.calls[0]["system"] is None
    assert "omnid-bin" not in adapter.calls[0]["env"]["PATH"]
    assert adapter.outputs == ["absent\n"]
    assert record["guidance"] == [] and record["success"] is False


def test_both_conditions_get_the_supplied_python_and_a_shim_that_cannot_import_omnidriver(tmp_path, fake_adapter):
    for condition in ("omnid", "bare"):
        adapter = fake_adapter(commands=["head -1 $(command -v solver)", "command -v python3", "command -v python"])
        setup = _setup(tmp_path, condition, output=tmp_path / f"out-{condition}")
        run_trial(_task(tmp_path), adapter, setup, 0)
        [folder] = (tmp_path / f"out-{condition}").iterdir()
        interpreter = adapter.outputs[0].strip()[2:]
        assert interpreter == str(setup.agent_python)
        assert subprocess.run([interpreter, "-c", "import omnidriver"]).returncode != 0
        assert adapter.outputs[1].strip() == str(folder / "tools/python3")
        assert adapter.outputs[2].strip() == str(folder / "tools/python")
        assert (folder / "tools/python3").resolve() == setup.agent_python.resolve()


def test_an_agent_python_that_imports_omnidriver_is_refused(tmp_path, fake_adapter):
    with pytest.raises(ValueError, match="agent_python"):
        run_trial(_task(tmp_path), fake_adapter(), _setup(tmp_path, "bare", agent_python=_python(tmp_path, 0, "py-ok")), 0)


def test_omnid_puts_only_omnidriver_on_the_path(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["command -v pytest || echo none", "command -v python3", "command -v omnidriver"])
    run_trial(_task(tmp_path), adapter, _setup(tmp_path, "omnid"), 0)
    folder = _folder(tmp_path)
    assert adapter.outputs == ["none\n", f"{folder}/tools/python3\n", f"{folder}/omnid-bin/omnidriver\n"]
    assert (folder / "omnid-bin/omnidriver").is_symlink()
    assert [p.name for p in (folder / "omnid-bin").iterdir()] == ["omnidriver"]


def test_the_agent_gets_a_dedicated_home_and_a_fixed_shell(tmp_path, fake_adapter):
    adapter = fake_adapter()
    setup = _setup(tmp_path, "bare", extra_env={"HOME": "/evil", "DYLD_LIBRARY_PATH": "/lib"})
    run_trial(_task(tmp_path), adapter, setup, 0)
    env = adapter.calls[0]["env"]
    assert (env["HOME"], env["SHELL"], env["DYLD_LIBRARY_PATH"]) == (str(setup.agent_home), "/bin/bash", "/lib")


@pytest.mark.parametrize("which", ["output", "agent_home"])
def test_a_folder_inside_a_repository_is_refused(tmp_path, fake_adapter, which):
    root = tmp_path / "gitroot"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    setup = _setup(tmp_path, "bare", **{which: root / "inside"})
    with pytest.raises(ValueError, match=which):
        run_trial(_task(tmp_path), fake_adapter(), setup, 0)


def test_a_trial_folder_name_says_nothing_of_the_condition(tmp_path, fake_adapter):
    for condition in ("omnid", "bare"):
        run_trial(_task(tmp_path), fake_adapter(), _setup(tmp_path, condition), 0)
    names = [p.name for p in (tmp_path / "out").iterdir()]
    assert len(names) == 2 and all(re.fullmatch(r"[0-9a-f]{32}", n) for n in names)


def test_an_adapter_that_raises_still_leaves_a_record(tmp_path, fake_adapter):
    record = run_trial(_task(tmp_path), fake_adapter(error=RuntimeError("boom")), _setup(tmp_path, "bare"), 0)
    assert "boom" in record["harness_error"] and record["success"] is False
    assert (_folder(tmp_path) / "task_record.json").exists()


def test_the_oracle_alone_gets_the_oracle_env(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["echo ${SECRET:-unset}"], answer={"P8": 42})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "bare", oracle_env={"SECRET": "s"}), 0)
    assert adapter.outputs == ["unset\n"] and "SECRET" not in adapter.calls[0]["env"]
    assert record["oracle"]["secret"] == "s" and record["success"] is True


@pytest.mark.parametrize("argv", [["/no/such/oracle"], [sys.executable, "-c", "import sys; sys.exit(3)"],
                                  [sys.executable, "-c", "print('not json')"]])
def test_an_oracle_that_cannot_judge_is_an_oracle_error(tmp_path, fake_adapter, argv):
    record = run_trial(_task(tmp_path, argv), fake_adapter(answer={"P8": 42}), _setup(tmp_path, "bare"), 0)
    assert "oracle_error" in record["oracle"] and record["success"] is False


def test_an_oracle_that_times_out_is_an_oracle_error(tmp_path, fake_adapter, monkeypatch):
    monkeypatch.setattr(trial, "ORACLE_TIMEOUT", 1)
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    record = run_trial(_task(tmp_path, argv), fake_adapter(), _setup(tmp_path, "bare"), 0)
    assert "oracle_error" in record["oracle"] and record["success"] is False


def test_git_failure_is_raised(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        _git(tmp_path, "rev-parse", "HEAD")


def _call(number, command):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": number, "name": "Bash", "input": {"command": command}}]}}


def _result(number, content):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": number, "content": content}]}}


def test_only_an_omnidriver_call_can_be_refused(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=['echo \'{"status": "failed"}\'', "omnidriver plan"])
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "omnid"), 0)
    assert record["refusals"] == 1


def test_refusals_read_compact_json_and_text_blocks_and_ignore_other_ids():
    transcript = [
        _call("a", "omnidriver run"), _result("a", '{"status":"failed"}'),
        _call("b", "omnidriver run"), _result("b", [{"type": "text", "text": "note"}, {"type": "text", "text": '{"status": "failed"}'}]),
        _call("c", "omnidriver run"), _result("c", '{"status": "passed"}'),
        _call("d", "ls"), _result("d", '{"status": "failed"}'),
        _result("e", '{"status": "failed"}'),
    ]
    assert _refusals(transcript) == 2
