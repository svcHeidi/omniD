import json
import os
import subprocess

from omnidriver_agents.shims import write_shims


def test_a_shim_runs_the_real_program_and_logs_it(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "solver").write_text("#!/bin/sh\necho ran \"$@\"\nexit 3\n")
    (real / "solver").chmod(0o755)
    shims = tmp_path / "shims"
    log = tmp_path / "launches.jsonl"
    write_shims(shims, ("solver",), log)
    env = {**os.environ, "PATH": f"{shims}:{real}:/usr/bin:/bin"}
    result = subprocess.run(["solver", "-x", "1"], env=env, capture_output=True, text=True)
    assert result.returncode == 3
    assert result.stdout == "ran -x 1\n"
    entry = json.loads(log.read_text())
    assert entry["program"] == "solver" and entry["argv"] == ["-x", "1"] and entry["exit_code"] == 3


def test_a_missing_program_is_logged_as_127(tmp_path):
    shims, log = tmp_path / "shims", tmp_path / "launches.jsonl"
    write_shims(shims, ("ghost",), log)
    env = {**os.environ, "PATH": f"{shims}:/usr/bin:/bin"}
    assert subprocess.run(["ghost"], env=env, capture_output=True).returncode == 127
    assert json.loads(log.read_text())["exit_code"] == 127
