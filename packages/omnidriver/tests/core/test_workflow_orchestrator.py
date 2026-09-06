import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from omnidriver.core.runtime.workflow_orchestrator import (
    backoff_delay,
    run_workflow,
)
from omnidriver.core.runtime.workflow_state import (
    WorkflowRunState,
    WorkflowStepState,
    replace_step_state,
    initial_workflow_state,
)


def _initial_state(step_id="solve"):
    step = WorkflowStepState(
        step_id=step_id, status="pending", attempt=0,
        command="cardiacFoam", args=(), cwd=".",
    )
    return WorkflowRunState(
        status="pending", current_step_id=step_id,
        completed_steps=(), failed_step_id=None, steps=(step,),
    )


def _dag(step_id="solve", retry_policy=None):
    step = {"id": step_id, "command": "cardiacFoam", "args": [], "cwd": "."}
    step["retry_policy"] = retry_policy if retry_policy is not None else {}
    return {"steps": [step]}


@dataclass
class _FakeResult:
    state: WorkflowRunState
    step_id: str
    exit_code: int | None
    stdout_log: str = "out.log"
    stderr_log: str = "err.log"


def _make_runner(outcomes):
    """outcomes: list of (status, exit_code, codes) consumed per call, in order."""
    state = {"n": 0}

    def runner(workflow_dag, run_state, step_id, *, case_root, log_dir,
               state_path=None, expected_artifacts=(), env=None):
        status, exit_code, codes = outcomes[state["n"]]
        state["n"] += 1
        prev = next((s for s in run_state.steps if s.step_id == step_id), None)
        attempt = (prev.attempt if prev else 0) + 1
        diagnostics = tuple({"level": "error", "code": c, "message": "x"} for c in codes)
        new_step = WorkflowStepState(
            step_id=step_id, status=status, attempt=attempt,
            command="cardiacFoam", args=(), cwd=".",
            exit_code=exit_code, diagnostics=diagnostics,
        )
        if status == "completed":
            new_state = replace_step_state(
                run_state, new_step, status="completed",
                current_step_id=None,
                completed_steps=run_state.completed_steps + (step_id,),
                failed_step_id=None,
            )
        else:
            new_state = replace_step_state(
                run_state, new_step, status="failed",
                current_step_id=step_id,
                completed_steps=run_state.completed_steps,
                failed_step_id=step_id,
            )
        result = _FakeResult(state=new_state, step_id=step_id, exit_code=exit_code)
        if state_path is not None:
            Path(state_path).write_text(json.dumps(new_state.to_json()))
        return result

    return runner, state


def test_backoff_delay_exponential_with_cap():
    assert backoff_delay(1, 2) == 2
    assert backoff_delay(2, 2) == 4
    assert backoff_delay(3, 2) == 8
    assert backoff_delay(10, 2, cap_seconds=60.0) == 60.0
    assert backoff_delay(5, 0) == 0


def test_timeout_retries_then_completes(tmp_path):
    runner, _ = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("completed", 0, []),
    ])
    sleeps = []
    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 2, "backoff_seconds": 1}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        runner=runner, sleep=sleeps.append,
    )
    assert outcome.state.status == "completed"
    summary = outcome.steps[0]
    assert summary["status"] == "ok"
    assert summary["attempts"] == 2
    assert sleeps == [1]  # backoff_delay(1, 1) == 1


def test_retryable_exhausts_attempts(tmp_path):
    runner, _ = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("failed", 1, ["workflow_step_timeout"]),
    ])
    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 2}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        runner=runner, sleep=lambda s: None,
    )
    assert outcome.state.status == "failed"
    assert outcome.steps[0]["attempts"] == 2
    assert outcome.steps[0]["status"] == "failed"


def test_fatal_failure_does_not_retry(tmp_path):
    runner, calls = _make_runner([
        ("failed", 0, ["missing_artifacts"]),  # exit 0 but failed
    ])
    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 5}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        runner=runner, sleep=lambda s: None,
    )
    assert calls["n"] == 1  # no retry
    assert outcome.state.status == "failed"
    assert outcome.steps[0]["status"] == "failed"  # NOT "ok" despite exit_code 0
    assert outcome.steps[0]["attempts"] == 1


def test_default_max_attempts_knob_enables_retry(tmp_path):
    runner, _ = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("completed", 0, []),
    ])
    outcome = run_workflow(
        _dag(retry_policy={}),  # empty policy -> falls back to default
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        default_max_attempts=2,
        runner=runner, sleep=lambda s: None,
    )
    assert outcome.state.status == "completed"
    assert outcome.steps[0]["attempts"] == 2


def test_max_attempts_one_bails_on_first_failure(tmp_path):
    runner, calls = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
    ])
    outcome = run_workflow(
        _dag(retry_policy={}),  # default_max_attempts default is 1
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        runner=runner, sleep=lambda s: None,
    )
    assert calls["n"] == 1
    assert outcome.state.status == "failed"


def test_max_total_attempts_caps_retries_below_per_step_budget(tmp_path):
    # Per-step budget is generous (5), but the whole-run ceiling is 2: the run
    # must stop after 2 total attempts even though the step would keep retrying.
    runner, calls = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("failed", 1, ["workflow_step_timeout"]),
        ("failed", 1, ["workflow_step_timeout"]),
    ])
    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 5}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        max_total_attempts=2,
        runner=runner, sleep=lambda s: None,
    )
    assert calls["n"] == 2  # stopped by the whole-run ceiling, not per-step
    assert outcome.state.status == "failed"
    assert outcome.steps[0]["attempts"] == 2


def test_max_total_attempts_none_preserves_per_step_behavior(tmp_path):
    # Default (None) must not change existing behavior: per-step max_attempts wins.
    runner, _ = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("completed", 0, []),
    ])
    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 2, "backoff_seconds": 1}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        max_total_attempts=None,
        runner=runner, sleep=lambda s: None,
    )
    assert outcome.state.status == "completed"
    assert outcome.steps[0]["attempts"] == 2


def test_persisted_state_is_resumable_between_retries(tmp_path):
    state_path = tmp_path / "workflow_state.json"
    captured = {}

    base_runner, _ = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("completed", 0, []),
    ])

    def runner(*args, **kwargs):
        result = base_runner(*args, **kwargs)
        # Snapshot the on-disk state right after the FIRST (failed) call.
        if "first" not in captured and result.exit_code != 0:
            captured["first"] = json.loads(state_path.read_text())
        return result

    def sleep(_seconds):
        # During backoff the persisted state must be resumable (pending), not failed.
        captured["during_backoff"] = json.loads(state_path.read_text())

    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 2, "backoff_seconds": 1}),
        _initial_state(),
        case_root=tmp_path, output_dir=tmp_path,
        state_path=state_path,
        runner=runner, sleep=sleep,
    )
    assert outcome.state.status == "completed"
    assert captured["during_backoff"]["status"] == "pending"
    assert captured["during_backoff"]["current_step_id"] == "solve"


@pytest.mark.parametrize("budget, executed", [(0, 0), (1, 1), (2, 2), (None, 2)])
def test_total_budget_is_checked_before_every_successful_dispatch(tmp_path, budget, executed):
    dag = {"steps": [
        {
            "id": name, "command": sys.executable,
            "args": ["-c", f"from pathlib import Path; Path('{name}').write_text('ran')"],
            "cwd": ".", "depends_on": [] if index == 0 else ["first"],
        }
        for index, name in enumerate(("first", "second"))
    ]}
    state = initial_workflow_state(dag)
    outcome = run_workflow(
        dag, state, case_root=tmp_path, output_dir=tmp_path / "output",
        max_total_attempts=budget,
    )
    assert (tmp_path / "first").exists() is (executed >= 1)
    assert (tmp_path / "second").exists() is (executed >= 2)
    assert sum(step.attempt for step in outcome.state.steps) == executed
    assert outcome.state.status == ("completed" if executed == 2 else "pending")
    saved = json.loads((tmp_path / "output" / "workflow_state.json").read_text())
    assert saved == outcome.state.to_json()


def test_explicit_context_reaches_each_runner_attempt(tmp_path):
    context = object()
    delegate, calls = _make_runner([
        ("failed", 1, ["workflow_step_timeout"]),
        ("completed", 0, []),
    ])
    received = []

    def runner(*args, driver_context, **kwargs):
        received.append(driver_context)
        return delegate(*args, **kwargs)

    outcome = run_workflow(
        _dag(retry_policy={"max_attempts": 2}), _initial_state(),
        case_root=tmp_path, output_dir=tmp_path, runner=runner,
        driver_context=context, sleep=lambda _: None,
    )
    assert outcome.state.status == "completed"
    assert calls["n"] == 2
    assert all(value is context for value in received)


def test_negative_budget_rejected_before_dispatch(tmp_path):
    def runner(*args, **kwargs):
        pytest.fail("negative budgets must not dispatch")

    with pytest.raises(ValueError, match="non-negative"):
        run_workflow(
            _dag(), _initial_state(), case_root=tmp_path, output_dir=tmp_path,
            runner=runner, max_total_attempts=-1,
        )
    assert not (tmp_path / "workflow_state.json").exists()


def test_resumed_invocation_gets_a_fresh_total_budget(tmp_path):
    dag = {"steps": [
        {"id": name, "command": sys.executable, "args": ["-c", "pass"],
         "cwd": ".", "depends_on": [] if name == "first" else ["first"]}
        for name in ("first", "second")
    ]}
    first = run_workflow(
        dag, initial_workflow_state(dag), case_root=tmp_path,
        output_dir=tmp_path, max_total_attempts=1,
    )
    assert first.state.status == "pending"
    resumed = run_workflow(
        dag, first.state, case_root=tmp_path, output_dir=tmp_path,
        max_total_attempts=1,
    )
    assert resumed.state.status == "completed"
    assert [step.attempt for step in resumed.state.steps] == [1, 1]
