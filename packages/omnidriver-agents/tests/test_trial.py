import json
import sys
from pathlib import Path

from omnidriver_agents.task import Oracle, Task
from omnidriver_agents.trial import TrialSetup, run_trial

ORACLE = """import json, sys
answer = json.load(open(sys.argv[1] + "/answer.json"))
print(json.dumps({"status": "passed" if answer.get("P8") == 42 else "failed"}))
"""


def _task(tmp_path):
    (tmp_path / "oracle.py").write_text(ORACLE)
    return Task(id="t", role="runner", brief="go", inputs={}, programs=("solver",), tree=None, wall_seconds=60,
                oracle=Oracle((sys.executable, str(tmp_path / "oracle.py"), "{trial}"), "status", ("passed",)),
                digest="d" * 64)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "agent-handbook").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("router")
    (repo / "agent-handbook/runner.md").write_text("runner")
    (repo / "agent-handbook/guidance-manifest.yaml").write_text(
        "version: 1\ncommon: [AGENTS.md]\nroles:\n  runner:\n    required: [agent-handbook/runner.md]\n")
    return repo


def _setup(tmp_path, condition):
    omnid_bin = tmp_path / "omnid-bin"
    omnid_bin.mkdir(exist_ok=True)
    (omnid_bin / "omnidriver").write_text("#!/bin/sh\necho '{\"status\": \"failed\", \"error\": \"x\"}'\n")
    (omnid_bin / "omnidriver").chmod(0o755)
    return TrialSetup(output=tmp_path / "out", condition=condition, omnid_repo=_repo(tmp_path),
                      omnidriver_bin=omnid_bin / "omnidriver", solver_path=(), extra_env={})


def test_omnid_gets_guidance_and_omnidriver_and_the_oracle_decides(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["omnidriver plan"], answer={"P8": 42})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "omnid"), 0)
    assert "router" in adapter.calls[0]["system"]
    assert [p for p, _ in record["guidance"]] == ["AGENTS.md", "agent-handbook/runner.md"]
    assert record["refusals"] == 1 and record["success"] is True
    folder = tmp_path / "out/t/fake/omnid/0"
    assert json.loads((folder / "task_record.json").read_text()) == record
    assert (folder / "transcript.jsonl").exists()


def test_bare_gets_no_guidance_and_no_omnidriver(tmp_path, fake_adapter):
    adapter = fake_adapter(commands=["command -v omnidriver || echo absent"], answer={"P8": 1})
    record = run_trial(_task(tmp_path), adapter, _setup(tmp_path, "bare"), 0)
    assert adapter.calls[0]["system"] is None
    assert "omnid-bin" not in adapter.calls[0]["env"]["PATH"]
    assert record["guidance"] == [] and record["success"] is False
