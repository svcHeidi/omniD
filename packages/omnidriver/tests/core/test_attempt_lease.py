"""Host-local ownership and recovery contracts for workflow attempts."""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from omnidriver.core.runtime.attempt_lease import (
    AttemptLeaseError,
    acquire_attempt_lease,
    acquire_case_lease,
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


def test_stale_recovery_cannot_delete_an_interleaved_live_owner(
    monkeypatch, tmp_path: Path,
) -> None:
    """A second contender cannot acquire between stale inspection and unlink."""
    import omnidriver.core.runtime.attempt_lease as lease_module

    path = tmp_path / ".omnidriver-attempt.lock"
    path.write_text(json.dumps({
        "hostname": socket.gethostname(), "pid": 12345, "token": "dead",
    }))
    monkeypatch.setattr(
        lease_module, "_pid_is_alive", lambda pid: pid != 12345,
    )
    original_read = lease_module._read_record
    stale_was_read = threading.Event()
    continue_recovery = threading.Event()
    first_read = True

    def paused_read(record_path: Path):
        nonlocal first_read
        record = original_read(record_path)
        if threading.current_thread().name == "recoverer" and first_read:
            first_read = False
            stale_was_read.set()
            assert continue_recovery.wait(timeout=2)
        return record

    monkeypatch.setattr(lease_module, "_read_record", paused_read)
    owner_acquired = threading.Event()
    release_owner = threading.Event()
    contender_result: list[str] = []

    def recoverer() -> None:
        with acquire_attempt_lease(tmp_path):
            owner_acquired.set()
            assert release_owner.wait(timeout=2)

    def contender() -> None:
        try:
            with acquire_attempt_lease(tmp_path):
                contender_result.append("acquired")
        except AttemptLeaseError:
            contender_result.append("blocked")

    owner = threading.Thread(target=recoverer, name="recoverer")
    owner.start()
    assert stale_was_read.wait(timeout=2)
    challenger = threading.Thread(target=contender, name="contender")
    challenger.start()
    time.sleep(0.05)
    assert contender_result == [], "contender bypassed in-progress stale recovery"
    continue_recovery.set()
    assert owner_acquired.wait(timeout=2)
    challenger.join(timeout=2)
    try:
        assert contender_result == ["blocked"]
        assert json.loads(path.read_text())["token"] != "dead"
    finally:
        release_owner.set()
        owner.join(timeout=2)
    assert not owner.is_alive()
    assert not challenger.is_alive()


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


def test_case_owner_blocks_run_through_a_different_output_directory(
    tmp_path: Path,
) -> None:
    dag = {
        "steps": [{
            "id": "run", "command": "ignored", "args": [], "cwd": ".",
            "depends_on": [],
        }],
    }
    state = initial_workflow_state(dag)
    assert state is not None
    case_root = tmp_path / "case"
    case_root.mkdir()

    with acquire_case_lease(case_root):
        with pytest.raises(AttemptLeaseError, match="case root is already owned"):
            run_workflow(
                dag,
                state,
                case_root=case_root,
                output_dir=tmp_path / "other-output",
            )
    assert not (tmp_path / "other-output" / ".omnidriver-attempt.lock").exists()


def test_case_lease_does_not_invent_a_missing_case_root(tmp_path: Path) -> None:
    case_root = tmp_path / "missing-case"
    with pytest.raises(AttemptLeaseError, match="case root does not exist"):
        with acquire_case_lease(case_root):
            pass
    assert not case_root.exists()


def test_claimed_preheld_leases_are_verified(tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    dag = {
        "steps": [{
            "id": "run", "command": "ignored", "args": [], "cwd": ".",
            "depends_on": [],
        }],
    }
    state = initial_workflow_state(dag)
    assert state is not None
    with pytest.raises(AttemptLeaseError, match="without owned"):
        run_workflow(
            dag,
            state,
            case_root=case_root,
            output_dir=tmp_path / "output",
            leases_held=True,
        )
