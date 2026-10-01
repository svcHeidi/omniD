"""The structured step executor: patch, replan, dispatch and the transaction it leaves."""
from __future__ import annotations

import stat
from dataclasses import replace
from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from omnidriver.core.runtime.execution_context import ReplannedExecution, StepExecutionContext
from omnidriver.core.runtime.remediation_transaction import (
    RemediationTransactionError,
    read_remediation_transaction,
)
from omnidriver.core.runtime.step_candidate import execute_step_candidate_owned
from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from plugins.minimal_plugin import MinimalTestPlugin


def _dag(command: str = "neutral") -> dict:
    return {"steps": [{
        "id": "run", "command": command, "args": [], "cwd": ".",
        "depends_on": [], "produces": [], "consumes": [],
    }]}


class _NeutralMutator(MinimalTestPlugin):
    def __init__(self, target: Path, events: list[str]) -> None:
        super().__init__(entrypoint="run-case")
        self.target = target
        self.events = events

    def _owned(self, case_root: Path) -> None:
        assert case_lease_is_held(case_root)
        assert attempt_lease_is_held(case_root.parent / "output")

    def get_override_target_paths(self, overrides, *, case_root, driver_context):
        del overrides, driver_context
        self._owned(case_root)
        self.events.append("targets")
        return (self.target,)

    def apply_overrides(
        self, overrides, *, case_root, driver_context, execution_env=None,
    ):
        del driver_context, execution_env
        self._owned(case_root)
        self.events.append("apply")
        self.target.write_text(str(overrides[0]["value"]) + "\n")
        return ()


def _fixture(tmp_path: Path):
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("1\n")
    output_dir = tmp_path / "output"
    events: list[str] = []
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    plugin = _NeutralMutator(target, events)
    context = StepExecutionContext(
        entry_label="neutral",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        driver_context=driver_context(plugin, source="test:step-candidate"),
        replan_after_mutation=lambda: _replan(case_root, output_dir, events, dag, state),
    )
    return context, target, events, state


def _replan(case_root, output_dir, events, dag, state):
    assert case_lease_is_held(case_root)
    assert attempt_lease_is_held(output_dir)
    events.append("replan")
    return ReplannedExecution(dag, state, ())


def _runner(state, events, *, successful: bool):
    def run(*args, **kwargs):
        del args
        assert kwargs["leases_held"] is True
        assert case_lease_is_held(kwargs["case_root"])
        assert attempt_lease_is_held(kwargs["state_path"].parent)
        events.append("dispatch")
        step = replace(
            state.steps[0],
            status="completed" if successful else "failed",
            attempt=2,
            exit_code=0 if successful else 7,
        )
        terminal = replace(
            state,
            status="completed" if successful else "failed",
            current_step_id=None,
            completed_steps=("run",) if successful else (),
            failed_step_id=None if successful else "run",
            steps=(step,),
        )
        return WorkflowStepRunResult(terminal, "run", step.exit_code, "out.log", "err.log")

    return run


_OVERRIDES = [{"driver_path": "value", "value": "2"}]


def _execute(context, **kwargs):
    with acquire_case_lease(context.case_root), acquire_attempt_lease(context.output_dir):
        return execute_step_candidate_owned(
            context, step_id="run", overrides=_OVERRIDES, hypothesis="change the neutral value",
            **kwargs,
        )


def test_success_applies_replans_dispatches_and_accepts(tmp_path):
    context, target, events, state = _fixture(tmp_path)
    result = _execute(context, run_step=_runner(state, events, successful=True))
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("succeeded", True)
    assert events == ["targets", "apply", "replan", "dispatch"]
    assert target.read_text() == "2\n"
    assert transaction["status"] == "accepted"
    assert transaction["execution_status"] == "ok"
    assert result.transaction_id == transaction["transaction_id"]
    assert (
        context.output_dir / "remediation_transactions" / f"{result.transaction_id}.json"
    ).is_file()


def test_neutral_utility_workflow_patches_and_dispatches_a_declared_case_script(tmp_path):
    context, target, events, state = _fixture(tmp_path)
    script = context.case_root / "run-case"
    script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test \"$(tr -d '\\n' < config)\" = 2\n"
        "mkdir -p postProcessing\n"
        "printf repaired > postProcessing/utility-report.txt\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    dag = _dag("run-case")
    utility_state = initial_workflow_state(dag)
    assert utility_state is not None
    context = replace(
        context,
        workflow_dag=dag,
        planned_state=utility_state,
        replan_after_mutation=lambda: _replan(
            context.case_root, context.output_dir, events, dag, utility_state,
        ),
    )
    result = _execute(context)

    assert (result.status, result.dispatched) == ("succeeded", True)
    assert (context.case_root / "postProcessing" / "utility-report.txt").read_text() == "repaired"
    assert events == ["targets", "apply", "replan"]
    assert read_remediation_transaction(context.case_root)["status"] == "accepted"


def test_changed_plan_rejects_written_candidate_before_dispatch(tmp_path):
    context, target, events, state = _fixture(tmp_path)
    changed = _dag("changed")
    context = replace(
        context,
        replan_after_mutation=lambda: ReplannedExecution(
            changed, initial_workflow_state(changed), (),
        ),
    )
    result = _execute(context, run_step=lambda *args, **kwargs: pytest.fail("dispatch must not run"))
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("rejected", False)
    assert "changed the workflow plan" in result.payload["error"]
    assert transaction["status"] == "rejected"
    assert Path(transaction["candidate_archive"], "config").read_text() == "2\n"
    assert target.read_text() == "2\n"


def test_failed_dispatch_rejects_the_transaction(tmp_path):
    context, target, events, state = _fixture(tmp_path)
    result = _execute(context, run_step=_runner(state, events, successful=False))
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("failed", True)
    assert transaction["status"] == "rejected"
    assert transaction["execution_status"] == "failed"
    assert transaction["execution_attempt"] == 2


def test_executor_crash_is_recorded_as_a_rejected_transaction(tmp_path):
    context, target, events, state = _fixture(tmp_path)

    def crash(*args, **kwargs):
        del args, kwargs
        events.append("dispatch")
        raise RuntimeError("executor disappeared")

    result = _execute(context, run_step=crash)
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("failed", True)
    assert result.payload["error"] == "executor disappeared"
    assert (transaction["status"], transaction["execution_status"]) == ("rejected", "error")
    assert target.read_text() == "2\n"


@pytest.mark.parametrize("held", ["case", "output"])
def test_unowned_execution_never_starts_a_transaction(tmp_path, held):
    context, target, events, state = _fixture(tmp_path)
    lease = (
        acquire_case_lease(context.case_root)
        if held == "case"
        else acquire_attempt_lease(context.output_dir)
    )
    with lease:
        with pytest.raises(RemediationTransactionError, match="owned case and output leases"):
            execute_step_candidate_owned(
                context, step_id="run", overrides=_OVERRIDES,
                run_step=_runner(state, events, successful=True),
            )

    assert target.read_text() == "1\n"
    assert events == []
    assert read_remediation_transaction(context.case_root) is None
