"""Adversarial tests for the structured, reservation-bound step executor."""
from __future__ import annotations

import json
import os
import stat
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

import omnidriver.core.runtime.remediation_transaction as transaction_module
import omnidriver.core.runtime.step_candidate as step_candidate_module
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.attempt_lease import (
    AttemptLeaseError,
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from omnidriver.core.runtime.execution_context import ReplannedExecution, StepExecutionContext
from omnidriver.core.runtime.fresh import ensure_fresh_output_dir
from omnidriver.core.runtime.remediation_transaction import read_remediation_transaction
from omnidriver.core.runtime.repair_loop import (
    RepairBudgets,
    RepairObservation,
    RepairProposal,
    RepairReservation,
    run_repair_loop,
)
from omnidriver.core.runtime.step_candidate import (
    execute_repair_candidate,
    repair_experiment_result,
)
from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def _dag(command: str = "neutral") -> dict:
    return {"steps": [{
        "id": "run", "command": command, "args": [], "cwd": ".",
        "depends_on": [], "produces": [], "consumes": [],
    }]}


class _NeutralMutator(MinimalOpenFOAMPlugin):
    def __init__(self, target: Path, events: list[str]) -> None:
        super().__init__()
        self.target = target
        self.events = events

    def _owned(self, case_root: Path) -> None:
        assert case_lease_is_held(case_root)
        assert attempt_lease_is_held(case_root.parent / "output")

    def get_override_target_paths(self, overrides, *, case_root):
        del overrides
        self._owned(case_root)
        self.events.append("targets")
        return (self.target,)

    def apply_overrides(self, overrides, *, case_root):
        self._owned(case_root)
        self.events.append("apply")
        self.target.write_text(str(overrides[0]["value"]) + "\n")


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
    observation = RepairObservation({"step_id": "run", "stderr_tail": ["old"]})
    proposal = RepairProposal(
        "change the neutral value",
        ({"driver_path": "value", "value": "2"},),
        observation.digest,
    )
    reservation = RepairReservation(
        str(uuid.uuid4()), 1, str(uuid.uuid4()), observation.digest, proposal.digest,
    )
    return context, target, events, state, observation, proposal, reservation


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


def test_stale_evidence_is_rejected_under_both_leases_before_mutation(tmp_path):
    context, target, events, state, old, proposal, reservation = _fixture(tmp_path)
    new = RepairObservation({"step_id": "run", "stderr_tail": ["new"]})

    def reobserve():
        assert case_lease_is_held(context.case_root)
        assert attempt_lease_is_held(context.output_dir)
        return new

    result = execute_repair_candidate(
        context, step_id="run", proposal=proposal, reservation=reservation,
        reobserve=reobserve, run_step=_runner(state, events, successful=True),
    )

    assert (result.status, result.dispatched, result.transaction_id) == (
        "rejected", False, None,
    )
    assert result.payload["repair_observation_digest"] == new.digest
    assert target.read_text() == "1\n"
    assert events == []
    assert read_remediation_transaction(context.case_root) is None
    (context.output_dir / "run_document.json").write_text("{}")
    assert ensure_fresh_output_dir(
        context.output_dir, fresh=True, allowed_root=tmp_path,
    ) is None
    with pytest.raises(RuntimeError, match="already claimed"):
        execute_repair_candidate(
            context, step_id="run", proposal=proposal, reservation=reservation,
            reobserve=lambda: old,
            run_step=_runner(state, events, successful=True),
        )


def test_success_binds_reservation_proposal_and_transaction(tmp_path):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    succeeded = RepairObservation({"step_id": "run", "status": "ok"})
    result = execute_repair_candidate(
        context, step_id="run", proposal=proposal, reservation=reservation,
        reobserve=lambda: observation if not events else succeeded,
        run_step=_runner(state, events, successful=True),
    )
    loop_result = repair_experiment_result(result, reservation)
    transaction = read_remediation_transaction(context.case_root)

    assert result.status == loop_result.status == "succeeded"
    assert result.dispatched is True
    assert events == ["targets", "apply", "replan", "dispatch"]
    assert target.read_text() == "2\n"
    assert transaction["status"] == "accepted"
    assert transaction["execution_status"] == "ok"
    assert transaction["proposal_digest"] == proposal.digest
    assert transaction["repair_binding"] == {
        "loop_id": reservation.loop_id,
        "execution": reservation.execution,
        "reservation_id": reservation.reservation_id,
        "observation_digest": reservation.observation_digest,
        "proposal_digest": reservation.proposal_digest,
    }
    assert result.transaction_id == loop_result.transaction_id == transaction["transaction_id"]
    durable = (
        context.output_dir / "remediation_transactions"
        / f"{result.transaction_id}.json"
    )
    assert durable.is_file()


def test_neutral_utility_workflow_repairs_and_dispatches_a_real_allrun(tmp_path):
    """One solver-neutral vertical slice: observe -> reserve -> repair -> run.

    ``Allrun`` is deliberately utility-only: it verifies the repaired case
    input and writes a report, without invoking a solver or cardiacFOAM.
    """
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    allrun = context.case_root / "Allrun"
    allrun.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test \"$(tr -d '\\n' < config)\" = 2\n"
        "mkdir -p postProcessing\n"
        "printf repaired > postProcessing/utility-report.txt\n"
    )
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)
    dag = _dag("Allrun")
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
    repaired = RepairObservation({"step_id": "run", "utility_report": "repaired"})
    result = execute_repair_candidate(
        context,
        step_id="run",
        proposal=proposal,
        reservation=reservation,
        reobserve=lambda: observation if not events else repaired,
    )

    transaction = read_remediation_transaction(context.case_root)
    assert result.status == "succeeded"
    assert result.dispatched is True
    assert (context.case_root / "postProcessing" / "utility-report.txt").read_text() == "repaired"
    assert events == ["targets", "apply", "replan"]
    assert transaction["status"] == "accepted"


def test_repair_loop_and_transaction_share_one_execution_identity(tmp_path):
    context, target, events, state, observation, proposal, _reservation = _fixture(tmp_path)
    succeeded = RepairObservation({"step_id": "run", "status": "ok"})

    def execute(candidate, reservation):
        result = execute_repair_candidate(
            context,
            step_id="run",
            proposal=candidate,
            reservation=reservation,
            reobserve=lambda: observation if not events else succeeded,
            run_step=_runner(state, events, successful=True),
        )
        return repair_experiment_result(result, reservation)

    outcome = run_repair_loop(
        observation,
        output_dir=context.output_dir,
        budgets=RepairBudgets(1),
        propose=lambda current: RepairProposal(
            proposal.hypothesis, proposal.overrides, current.digest,
        ),
        execute_candidate=execute,
    )
    transaction = read_remediation_transaction(context.case_root)
    journal = json.loads(outcome.journal_path.read_text())
    experiment = journal["experiments"][0]
    binding = transaction["repair_binding"]
    assert outcome.status == "succeeded"
    assert experiment["transaction_id"] == transaction["transaction_id"]
    assert experiment["reservation_id"] == binding["reservation_id"]
    assert experiment["execution"] == binding["execution"]
    assert experiment["observation_digest"] == binding["observation_digest"]
    assert experiment["proposal_digest"] == binding["proposal_digest"]


def test_restart_recovers_terminal_transaction_before_callback_return(
    monkeypatch, tmp_path,
):
    context, target, events, state, observation, proposal, _reservation = _fixture(tmp_path)
    succeeded = RepairObservation({"step_id": "run", "status": "ok"})
    loop_id = str(uuid.uuid4())
    real_complete = step_candidate_module.complete_repair_reservation

    def disappear(*args, **kwargs):
        del args, kwargs
        raise KeyboardInterrupt("process disappeared after terminal transaction")

    monkeypatch.setattr(step_candidate_module, "complete_repair_reservation", disappear)

    def execute(candidate, reservation):
        result = execute_repair_candidate(
            context, step_id="run", proposal=candidate, reservation=reservation,
            reobserve=lambda: observation if not events else succeeded,
            run_step=_runner(state, events, successful=True),
        )
        return repair_experiment_result(result, reservation)

    with pytest.raises(KeyboardInterrupt):
        run_repair_loop(
            observation, output_dir=context.output_dir, budgets=RepairBudgets(1),
            propose=lambda current: RepairProposal(
                proposal.hypothesis, proposal.overrides, current.digest,
            ),
            execute_candidate=execute, loop_id=loop_id,
        )
    assert read_remediation_transaction(context.case_root)["status"] == "accepted"

    monkeypatch.setattr(
        step_candidate_module, "complete_repair_reservation", real_complete,
    )
    outcome = run_repair_loop(
        observation, output_dir=context.output_dir, budgets=RepairBudgets(1),
        propose=lambda current: pytest.fail("terminal reservation must be reconciled"),
        execute_candidate=lambda candidate, reservation: pytest.fail(
            "terminal reservation must not execute again"
        ),
        loop_id=loop_id,
    )
    journal = json.loads(outcome.journal_path.read_text())
    assert (outcome.status, outcome.reason) == ("succeeded", "candidate_succeeded")
    assert journal["experiments"][0]["recovered_from_reservation"] is True


def test_restart_repairs_torn_terminal_transaction_mirror(monkeypatch, tmp_path):
    context, target, events, state, observation, proposal, _reservation = _fixture(tmp_path)
    succeeded = RepairObservation({"step_id": "run", "status": "ok"})
    loop_id = str(uuid.uuid4())
    real_write = transaction_module._atomic_write

    def tear_after_case_head(path, payload):
        if (
            payload.get("status") == "accepted"
            and path.parent.name == "remediation_transactions"
        ):
            raise KeyboardInterrupt("crash between case head and output mirror")
        return real_write(path, payload)

    monkeypatch.setattr(transaction_module, "_atomic_write", tear_after_case_head)

    def execute(candidate, reservation):
        result = execute_repair_candidate(
            context, step_id="run", proposal=candidate, reservation=reservation,
            reobserve=lambda: observation if not events else succeeded,
            run_step=_runner(state, events, successful=True),
        )
        return repair_experiment_result(result, reservation)

    with pytest.raises(KeyboardInterrupt):
        run_repair_loop(
            observation, output_dir=context.output_dir, budgets=RepairBudgets(1),
            propose=lambda current: RepairProposal(
                proposal.hypothesis, proposal.overrides, current.digest,
            ),
            execute_candidate=execute, loop_id=loop_id,
        )
    head = read_remediation_transaction(context.case_root)
    durable_path = (
        context.output_dir / "remediation_transactions"
        / f"{head['transaction_id']}.json"
    )
    assert head["status"] == "accepted"
    assert json.loads(durable_path.read_text())["status"] == "dispatching"

    monkeypatch.setattr(transaction_module, "_atomic_write", real_write)
    later_proposal = RepairProposal(
        "later loop replaces the case head",
        ({"driver_path": "value", "value": "3"},),
        succeeded.digest,
    )
    later_reservation = RepairReservation(
        str(uuid.uuid4()), 1, str(uuid.uuid4()),
        succeeded.digest, later_proposal.digest,
    )
    later = execute_repair_candidate(
        context, step_id="run", proposal=later_proposal,
        reservation=later_reservation, reobserve=lambda: succeeded,
        run_step=_runner(state, events, successful=True),
    )
    later_head = read_remediation_transaction(context.case_root)
    assert later_head["transaction_id"] == later.transaction_id

    outcome = run_repair_loop(
        observation, output_dir=context.output_dir, budgets=RepairBudgets(1),
        propose=lambda current: pytest.fail("torn terminal state must reconcile"),
        execute_candidate=lambda candidate, reservation: pytest.fail(
            "torn terminal state must not execute again"
        ),
        loop_id=loop_id,
    )
    assert outcome.status == "succeeded"
    assert json.loads(durable_path.read_text()) == head
    assert read_remediation_transaction(context.case_root) == later_head


def test_changed_plan_rejects_written_candidate_before_dispatch(tmp_path):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    changed = _dag("changed")
    changed_state = initial_workflow_state(changed)
    context = replace(
        context,
        replan_after_mutation=lambda: ReplannedExecution(changed, changed_state, ()),
    )
    result = execute_repair_candidate(
        context, step_id="run", proposal=proposal, reservation=reservation,
        reobserve=lambda: observation,
        run_step=lambda *args, **kwargs: pytest.fail("dispatch must not run"),
    )
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("rejected", False)
    assert "changed the workflow plan" in result.payload["error"]
    assert transaction["status"] == "rejected"
    assert Path(transaction["candidate_archive"], "config").read_text() == "2\n"
    assert target.read_text() == "2\n"


def test_failed_dispatch_returns_new_observation_and_rejects_transaction(tmp_path):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    failed = RepairObservation({"step_id": "run", "stderr_tail": ["new failure"]})
    result = execute_repair_candidate(
        context, step_id="run", proposal=proposal, reservation=reservation,
        reobserve=lambda: observation if "dispatch" not in events else failed,
        run_step=_runner(state, events, successful=False),
    )
    transaction = read_remediation_transaction(context.case_root)

    assert (result.status, result.dispatched) == ("failed", True)
    assert result.payload["repair_observation_digest"] == failed.digest
    assert transaction["status"] == "rejected"
    assert transaction["execution_status"] == "failed"
    assert transaction["execution_attempt"] == 2


def test_executor_crash_after_dispatch_admission_remains_recoverable(tmp_path):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)

    def crash(*args, **kwargs):
        del args, kwargs
        events.append("dispatch")
        raise RuntimeError("executor disappeared")

    with pytest.raises(RuntimeError, match="executor disappeared"):
        execute_repair_candidate(
            context, step_id="run", proposal=proposal, reservation=reservation,
            reobserve=lambda: observation, run_step=crash,
        )

    transaction = read_remediation_transaction(context.case_root)
    assert transaction["status"] == "dispatching"
    assert transaction["repair_binding"]["reservation_id"] == reservation.reservation_id
    assert target.read_text() == "2\n"


def test_duplicate_reserved_callback_cannot_replace_terminal_transaction(tmp_path):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    succeeded = RepairObservation({"step_id": "run", "status": "ok"})
    first = execute_repair_candidate(
        context, step_id="run", proposal=proposal, reservation=reservation,
        reobserve=lambda: observation if not events else succeeded,
        run_step=_runner(state, events, successful=True),
    )
    first_transaction = read_remediation_transaction(context.case_root)
    second_proposal = RepairProposal(
        "a later repair loop",
        ({"driver_path": "value", "value": "3"},),
        succeeded.digest,
    )
    second_reservation = RepairReservation(
        str(uuid.uuid4()), 1, str(uuid.uuid4()),
        succeeded.digest, second_proposal.digest,
    )
    second = execute_repair_candidate(
        context, step_id="run", proposal=second_proposal,
        reservation=second_reservation, reobserve=lambda: succeeded,
        run_step=_runner(state, events, successful=True),
    )
    current = read_remediation_transaction(context.case_root)

    with pytest.raises(RuntimeError, match="already claimed"):
        execute_repair_candidate(
            context, step_id="run", proposal=proposal, reservation=reservation,
            reobserve=lambda: observation,
            run_step=pytest.fail,
        )

    assert read_remediation_transaction(context.case_root) == current
    assert first.transaction_id == first_transaction["transaction_id"]
    assert second.transaction_id == current["transaction_id"]


@pytest.mark.parametrize("held", ["case", "output"])
def test_lease_conflict_never_starts_a_transaction(tmp_path, held):
    context, target, events, state, observation, proposal, reservation = _fixture(tmp_path)
    lease = (
        acquire_case_lease(context.case_root)
        if held == "case"
        else acquire_attempt_lease(context.output_dir)
    )
    with lease:
        with pytest.raises(AttemptLeaseError):
            execute_repair_candidate(
                context, step_id="run", proposal=proposal, reservation=reservation,
                reobserve=lambda: observation,
                run_step=_runner(state, events, successful=True),
            )

    assert target.read_text() == "1\n"
    assert events == []
    assert read_remediation_transaction(context.case_root) is None
    with acquire_case_lease(context.case_root):
        assert case_lease_is_held(context.case_root)
