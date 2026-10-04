"""A run that is stopped, timed out or killed leaves no solver behind, and a later resume knows what happened.

Every step here is a fake long-running process (``sleep``); no test runs a solver."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.runtime.sweep_runner import _run_case_process
from omnidriver.core.runtime.workflow_runner import (
    settle_interrupted_steps,
    terminate_recorded_steps,
)
from omnidriver.core.runtime.workflow_state import initial_workflow_state, workflow_state_from_json
from plugins.toy import SLEEPING_PLUGIN, write_toy_native_case

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone(process: subprocess.Popen, seconds: float = 5.0) -> bool:
    try:
        process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _own_session_sleep() -> subprocess.Popen:
    return subprocess.Popen(["sleep", "60"], start_new_session=True)


def _state_running(step_pid: int | None, *, hostname: str | None = None) -> dict:
    dag = {"steps": [{"id": "solve", "command": "sleep", "args": ["60"], "cwd": ".", "depends_on": []}]}
    state = initial_workflow_state(dag).to_json()
    state.update(status="running", current_step_id="solve")
    state["steps"][0].update(status="running", attempt=1, host={"hostname": hostname or socket.gethostname()})
    if step_pid is not None:
        state["steps"][0]["pid"] = step_pid
    return state


def test_a_case_timeout_ends_the_step_the_case_started_in_its_own_session(tmp_path):
    step = _own_session_sleep()
    state_path = tmp_path / "workflow_state.json"
    state_path.write_text(json.dumps(_state_running(step.pid)))
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            _run_case_process(["sleep", "60"], env=dict(os.environ), timeout=0.5, state_path=state_path)
        assert _gone(step), "the step outlived the timed-out case"
    finally:
        step.kill()
        step.wait()


def test_a_recorded_pid_that_is_not_a_step_of_its_own_is_never_signalled(tmp_path):
    bystander = subprocess.Popen(["sleep", "60"])
    state_path = tmp_path / "workflow_state.json"
    state_path.write_text(json.dumps(_state_running(bystander.pid)))
    try:
        terminate_recorded_steps(state_path)
        time.sleep(0.2)
        assert bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait()


def test_a_step_left_running_by_a_dead_process_is_failed_as_interrupted_and_keeps_its_attempt(tmp_path):
    dead = subprocess.Popen(["true"], start_new_session=True)
    dead.wait()
    state_path = tmp_path / "workflow_state.json"
    state = workflow_state_from_json(_state_running(dead.pid))

    settled = settle_interrupted_steps(state, state_path)

    (step,) = settled.steps
    assert (settled.status, settled.failed_step_id, step.status, step.attempt) == ("failed", "solve", "failed", 1)
    assert step.diagnostics[-1]["code"] == "workflow_step_interrupted"
    assert step.pid is None
    assert workflow_state_from_json(json.loads(state_path.read_text())) == settled


def test_a_step_that_is_still_running_is_never_marked_interrupted(tmp_path):
    live = _own_session_sleep()
    try:
        with pytest.raises(ValueError, match=rf"still running \(pid {live.pid}\)"):
            settle_interrupted_steps(
                workflow_state_from_json(_state_running(live.pid)), tmp_path / "workflow_state.json",
            )
        assert not (tmp_path / "workflow_state.json").exists()
    finally:
        live.kill()
        live.wait()


def test_a_step_started_on_another_host_cannot_be_known_to_have_stopped(tmp_path):
    with pytest.raises(ValueError, match="another-host"):
        settle_interrupted_steps(
            workflow_state_from_json(_state_running(1, hostname="another-host")), tmp_path / "workflow_state.json",
        )


def _planned_sleeping_case(tmp_path: Path) -> Path:
    write_toy_native_case(tmp_path / "native")
    assert main([
        "plan", "--strict", "--plugin", SLEEPING_PLUGIN, "--entry", "toyTutorial",
        "--cases-root", str(tmp_path / "native"), "--scratch-dir", str(tmp_path / "scratch"),
    ]) == 0
    return tmp_path / "scratch" / "records" / "toyTutorial"


def _wait_for_running_pid(state_path: Path) -> int:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            (step,) = json.loads(state_path.read_text())["steps"]
        except (OSError, ValueError):
            step = {}
        if step.get("status") == "running" and "pid" in step:
            return step["pid"]
        time.sleep(0.05)
    raise AssertionError("the step never started")


@pytest.mark.parametrize("sent", [signal.SIGTERM, signal.SIGINT])
def test_a_signal_to_the_cli_ends_the_running_step_and_records_it_cancelled(tmp_path, capsys, sent):
    case = _planned_sleeping_case(tmp_path)
    capsys.readouterr()
    run = subprocess.Popen(
        [sys.executable, "-m", "omnidriver", "run", "--plugin", SLEEPING_PLUGIN,
         "--run-document", str(case / "run_document.json")],
        stdout=subprocess.PIPE, text=True,
    )
    step_pid = None
    try:
        step_pid = _wait_for_running_pid(case / "workflow_state.json")
        run.send_signal(sent)
        output, _ = run.communicate(timeout=30)
        deadline = time.monotonic() + 5
        while _alive(step_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(step_pid), "the step outlived the CLI"
        state = json.loads((case / "workflow_state.json").read_text())
        (step,) = state["steps"]
        assert step["status"] == "failed" and "pid" not in step
        assert [d["code"] for d in step["diagnostics"]] == ["workflow_step_cancelled"]
        assert run.returncode == 1 and json.loads(output)["status"] == "failed"
    finally:
        if run.poll() is None:
            run.kill()
        if step_pid is not None and _alive(step_pid):
            os.killpg(step_pid, signal.SIGKILL)


def test_resuming_after_the_cli_was_killed_reruns_the_step_as_a_new_attempt_with_its_logs_kept(tmp_path, capsys):
    case = _planned_sleeping_case(tmp_path)
    capsys.readouterr()
    document = str(case / "run_document.json")
    first = subprocess.Popen(
        [sys.executable, "-m", "omnidriver", "run", "--plugin", SLEEPING_PLUGIN, "--run-document", document],
        stdout=subprocess.DEVNULL,
    )
    first_pid = _wait_for_running_pid(case / "workflow_state.json")
    first.kill()
    first.wait()
    os.killpg(first_pid, signal.SIGKILL)
    while _alive(first_pid):
        time.sleep(0.05)
    assert (case / "workflow_logs" / "solve.attempt1.stdout.log").exists()

    assert main(["run", "--plugin", SLEEPING_PLUGIN, "--run-document", document]) == 1
    refusal = json.loads(capsys.readouterr().out)
    assert "use action=step" in refusal["error"]
    (step,) = refusal["workflow_state"]["steps"]
    assert (step["status"], step["attempt"]) == ("failed", 1)
    assert step["diagnostics"][-1]["code"] == "workflow_step_interrupted"

    second = subprocess.Popen(
        [sys.executable, "-m", "omnidriver", "step", "--plugin", SLEEPING_PLUGIN, "--run-document", document,
         "--step", "solve"],
        stdout=subprocess.DEVNULL,
    )
    second_pid = None
    try:
        deadline = time.monotonic() + 30
        while second_pid is None and time.monotonic() < deadline:
            (step,) = json.loads((case / "workflow_state.json").read_text())["steps"]
            second_pid = step["pid"] if step["status"] == "running" and step["attempt"] == 2 else None
            time.sleep(0.05)
        assert second_pid is not None, "the rerun never started"
        assert (case / "workflow_logs" / "solve.attempt1.stdout.log").exists()
        assert (case / "workflow_logs" / "solve.attempt2.stdout.log").exists()
    finally:
        second.terminate()
        second.wait(timeout=30)
        if second_pid is not None and _alive(second_pid):
            os.killpg(second_pid, signal.SIGKILL)
