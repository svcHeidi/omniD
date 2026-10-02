"""The structured step executor: edit, replan, dispatch."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from omnidriver.core.case_transaction import CaseTransactionError
from omnidriver.core.runtime.attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from omnidriver.core.runtime.execution_context import ReplannedExecution, StepExecutionContext
from omnidriver.core.runtime.step_execution import execute_step_owned
from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
from omnidriver.core.runtime.workflow_state import initial_workflow_state


def _dag(command: str = "neutral") -> dict:
    return {"steps": [{
        "id": "run", "command": command, "args": [], "cwd": ".",
        "depends_on": [], "produces": [], "consumes": [],
    }]}


def _fixture(tmp_path: Path):
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    events: list[str] = []

    def apply_study(study):
        assert case_lease_is_held(case_root) and attempt_lease_is_held(output_dir)
        events.append("apply")
        return ({"document": "d", "key_path": ["k"], "value": study["d:k"], "status": "changed"},)

    def replan():
        events.append("replan")
        return ReplannedExecution(dag, state, ())

    context = StepExecutionContext(
        entry_label="neutral", workflow_dag=dag, planned_state=state, case_root=case_root,
        output_dir=output_dir, expected_artifacts=(), apply_study=apply_study,
        replan_after_mutation=replan,
    )
    return context, events, state


def _runner(state, events, *, successful: bool):
    def run(*args, **kwargs):
        del args
        assert kwargs["leases_held"] is True
        events.append("dispatch")
        step = replace(
            state.steps[0], status="completed" if successful else "failed",
            attempt=2, exit_code=0 if successful else 7,
        )
        terminal = replace(
            state, status="completed" if successful else "failed", current_step_id=None,
            completed_steps=("run",) if successful else (),
            failed_step_id=None if successful else "run", steps=(step,),
        )
        return WorkflowStepRunResult(terminal, "run", step.exit_code, "out.log", "err.log")

    return run


def _execute(context, **kwargs):
    with acquire_case_lease(context.case_root), acquire_attempt_lease(context.output_dir):
        return execute_step_owned(context, step_id="run", study={"d:k": 2}, **kwargs)


def _audit(context) -> list[dict]:
    path = context.output_dir / "remediation_history.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_success_edits_replans_dispatches_and_audits(tmp_path):
    context, events, state = _fixture(tmp_path)
    result = _execute(context, run_step=_runner(state, events, successful=True))

    assert result.status == "succeeded"
    assert events == ["apply", "replan", "dispatch"]
    assert result.payload["applied_patches"][0]["value"] == 2
    (record,) = _audit(context)
    assert (record["resulting_status"], record["attempt"]) == ("ok", 2)


def test_a_step_with_no_edit_touches_nothing(tmp_path):
    context, events, state = _fixture(tmp_path)
    with acquire_case_lease(context.case_root), acquire_attempt_lease(context.output_dir):
        result = execute_step_owned(
            context, step_id="run", run_step=_runner(state, events, successful=True),
        )

    assert (result.status, events) == ("succeeded", ["dispatch"])
    assert "applied_patches" not in result.payload
    assert not (context.output_dir / "remediation_history.jsonl").exists()


def test_a_changed_plan_refuses_to_dispatch_and_says_the_edit_stays(tmp_path):
    context, events, state = _fixture(tmp_path)
    changed = _dag("changed")
    context = replace(
        context,
        replan_after_mutation=lambda: ReplannedExecution(changed, initial_workflow_state(changed), ()),
    )
    result = _execute(context, run_step=lambda *a, **k: pytest.fail("dispatch must not run"))

    assert result.status == "rejected"
    assert "changed the workflow plan" in result.payload["error"]
    assert _audit(context)[0]["resulting_status"] == "replan_error"


def test_a_refused_edit_dispatches_nothing_and_audits_nothing(tmp_path):
    context, events, state = _fixture(tmp_path)

    def refuse(study):
        raise CaseTransactionError("commit failed; rolled back")

    result = _execute(
        replace(context, apply_study=refuse),
        run_step=lambda *a, **k: pytest.fail("dispatch must not run"),
    )

    assert result.status == "rejected"
    assert "commit failed; rolled back" in result.payload["error"]
    assert not (context.output_dir / "remediation_history.jsonl").exists()


def test_a_failed_step_reports_the_failure_and_audits_it(tmp_path):
    context, events, state = _fixture(tmp_path)
    result = _execute(context, run_step=_runner(state, events, successful=False))

    assert result.status == "failed"
    assert result.payload["failure_context"]["exit_code"] == 7
    assert _audit(context)[0]["resulting_status"] == "failed"


def test_an_executor_crash_is_audited(tmp_path):
    context, events, state = _fixture(tmp_path)

    def crash(*args, **kwargs):
        raise RuntimeError("executor disappeared")

    result = _execute(context, run_step=crash)

    assert result.status == "failed"
    assert result.payload["error"] == "executor disappeared"
    assert _audit(context)[0]["resulting_status"] == "rerun_error"


@pytest.mark.parametrize("held", ["case", "output"])
def test_unowned_execution_never_edits(tmp_path, held):
    context, events, state = _fixture(tmp_path)
    lease = (
        acquire_case_lease(context.case_root) if held == "case"
        else acquire_attempt_lease(context.output_dir)
    )
    with lease:
        with pytest.raises(RuntimeError, match="owned case and output leases"):
            execute_step_owned(
                context, step_id="run", study={"d:k": 2},
                run_step=_runner(state, events, successful=True),
            )

    assert events == []
