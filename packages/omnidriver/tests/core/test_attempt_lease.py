"""Host-local ownership and recovery contracts for workflow attempts."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from omnidriver.core.runtime.attempt_lease import (
    AttemptLeaseError,
    acquire_attempt_lease,
)
from omnidriver.core.runtime.workflow_orchestrator import run_workflow
from omnidriver.core.runtime.workflow_state import initial_workflow_state


def test_active_owner_blocks_a_second_attempt(tmp_path: Path) -> None:
    with acquire_attempt_lease(tmp_path):
        with pytest.raises(AttemptLeaseError, match="already owned"):
            with acquire_attempt_lease(tmp_path):
                pass
    assert not (tmp_path / ".omnidriver-attempt.lock").exists()


def test_dead_same_host_owner_is_recovered(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / ".omnidriver-attempt.lock"
    path.write_text(json.dumps({"hostname": socket.gethostname(), "pid": 12345, "token": "dead"}))
    monkeypatch.setattr("omnidriver.core.runtime.attempt_lease._pid_is_alive", lambda _: False)
    with acquire_attempt_lease(tmp_path) as lease:
        assert lease.path == path
        assert json.loads(path.read_text())["token"] == lease.token
    assert not path.exists()


def test_remote_or_malformed_owner_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / ".omnidriver-attempt.lock"
    path.write_text(json.dumps({"hostname": "other-host", "pid": 12345, "token": "remote"}))
    with pytest.raises(AttemptLeaseError, match="already owned"):
        with acquire_attempt_lease(tmp_path):
            pass
    path.write_text("not json")
    with pytest.raises(AttemptLeaseError, match="unreadable or remote"):
        with acquire_attempt_lease(tmp_path):
            pass


def test_run_workflow_holds_lease_for_the_whole_attempt(tmp_path: Path) -> None:
    dag = {"steps": [{"id": "run", "command": "ignored", "args": [], "cwd": ".", "depends_on": []}]}
    state = initial_workflow_state(dag)
    assert state is not None

    def runner(*args, **kwargs):
        del args, kwargs
        with pytest.raises(AttemptLeaseError):
            with acquire_attempt_lease(tmp_path / "output"):
                pass
        step = state.steps[0]
        from dataclasses import replace
        from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
        completed = replace(
            state, status="completed", current_step_id=None, completed_steps=("run",),
            steps=(replace(step, status="completed", attempt=1, exit_code=0),),
        )
        return WorkflowStepRunResult(completed, "run", 0, "out", "err")

    outcome = run_workflow(
        dag, state, case_root=tmp_path, output_dir=tmp_path / "output", runner=runner,
    )
    assert outcome.state.status == "completed"
    assert not (tmp_path / "output" / ".omnidriver-attempt.lock").exists()
