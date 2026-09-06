"""Solver-free process execution contracts for the workflow runner.

These tests intentionally use only the Python interpreter.  They exercise the
generic runner's ownership and recovery boundaries; no OpenFOAM runtime is
needed.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state


def _dag(args: list[str], *, timeout_s: int | None = None) -> dict:
    step = {
        "id": "run",
        "command": sys.executable,
        "args": args,
        "cwd": ".",
        "depends_on": [],
        "produces": [],
        "consumes": [],
        "retry_policy": {"max_attempts": 2},
        "command_display": sys.executable,
    }
    if timeout_s is not None:
        step["timeout_s"] = timeout_s
    return {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [step],
    }


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_timeout_records_retryable_diagnostic_and_does_not_leave_descendant(
    tmp_path: Path,
) -> None:
    """A timed-out step must own and clean up its entire child process tree."""
    pid_file = tmp_path / "child.pid"
    code = (
        "import pathlib, subprocess, sys, time; "
        f"p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
        "time.sleep(30)"
    )
    dag = _dag(["-c", code], timeout_s=1)
    state = initial_workflow_state(dag)
    assert state is not None

    result = run_workflow_step(dag, state, "run", case_root=tmp_path, log_dir=tmp_path / "logs")
    payload = result.state.to_json()
    assert payload["status"] == "failed"
    assert payload["steps"][0]["exit_code"] is None
    assert any(d["code"] == "workflow_step_timeout" for d in payload["steps"][0]["diagnostics"])

    # Give process-group cleanup a short, deterministic settling window.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not pid_file.exists():
        time.sleep(0.02)
    assert pid_file.exists(), "fixture child did not start"
    child_pid = int(pid_file.read_text())
    try:
        while time.monotonic() < deadline and _pid_exists(child_pid):
            time.sleep(0.02)
        assert not _pid_exists(child_pid), "timed-out descendant survived runner cleanup"
    finally:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="process-group ownership is POSIX-only")
def test_timeout_escalates_after_parent_exits_but_term_ignoring_child_survives(
    tmp_path: Path,
) -> None:
    """SIGKILL escalation is based on the group, not direct-parent liveness."""
    pid_file = tmp_path / "term-ignoring-child.pid"
    child_code = (
        "import os, pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(30)"
    )
    dag = _dag(["-c", parent_code], timeout_s=1)
    state = initial_workflow_state(dag)
    assert state is not None

    result = run_workflow_step(
        dag, state, "run", case_root=tmp_path, log_dir=tmp_path / "logs"
    )
    assert any(
        diagnostic["code"] == "workflow_step_timeout"
        for diagnostic in result.state.steps[0].diagnostics
    )
    assert pid_file.exists(), "fixture child did not install its SIGTERM handler"
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    try:
        while time.monotonic() < deadline and _pid_exists(child_pid):
            time.sleep(0.02)
        assert not _pid_exists(child_pid), "SIGTERM-ignoring descendant survived cleanup"
    finally:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_completed_step_cannot_be_replayed_without_new_owned_state(tmp_path: Path) -> None:
    dag = _dag(["-c", "pass"])
    state = initial_workflow_state(dag)
    assert state is not None
    completed = run_workflow_step(dag, state, "run", case_root=tmp_path, log_dir=tmp_path / "logs").state
    assert completed.steps[0].status == "completed"
    with pytest.raises(ValueError, match="only pending or failed"):
        run_workflow_step(dag, completed, "run", case_root=tmp_path, log_dir=tmp_path / "logs")


def test_cancellation_cleans_owned_descendants(tmp_path: Path) -> None:
    """Caller cancellation has the same process-tree guarantee as timeout."""
    pid_file = tmp_path / "cancelled-child.pid"
    code = (
        "import pathlib, subprocess, sys, time; "
        "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
        "time.sleep(30)"
    )
    cancelled = threading.Event()
    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    try:
        result = run_workflow_step(
            _dag(["-c", code]), initial_workflow_state(_dag(["-c", code])), "run",
            case_root=tmp_path, log_dir=tmp_path / "logs",
            cancellation_requested=cancelled.is_set,
        )
    finally:
        timer.cancel()
    assert any(d["code"] == "workflow_step_cancelled" for d in result.state.steps[0].diagnostics)
    assert pid_file.exists()
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    try:
        while time.monotonic() < deadline and _pid_exists(child_pid):
            time.sleep(0.02)
        assert not _pid_exists(child_pid), "cancelled descendant survived runner cleanup"
    finally:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_retry_attempt_requires_failed_state_and_preserves_attempt_ownership(tmp_path: Path) -> None:
    dag = _dag(["-c", "import sys; sys.exit(3)"])
    state = initial_workflow_state(dag)
    assert state is not None
    failed = run_workflow_step(dag, state, "run", case_root=tmp_path, log_dir=tmp_path / "logs").state
    assert failed.steps[0].status == "failed"
    retried = run_workflow_step(dag, failed, "run", case_root=tmp_path, log_dir=tmp_path / "logs").state
    assert retried.steps[0].attempt == 2
    assert (tmp_path / "logs" / "run.attempt1.stdout.log").exists()
    assert (tmp_path / "logs" / "run.attempt2.stdout.log").exists()


def test_workflow_digest_mismatch_blocks_recovery_attempt(tmp_path: Path) -> None:
    dag = _dag(["-c", "pass"])
    state = initial_workflow_state(dag)
    assert state is not None
    changed = _dag(["-c", "print('changed')"])
    with pytest.raises(ValueError, match="different DAG"):
        run_workflow_step(changed, state, "run", case_root=tmp_path, log_dir=tmp_path / "logs")
