from __future__ import annotations

import json

import pytest

from omnidriver.core.runtime.repair_loop import (
    RepairBudgets,
    RepairExperimentResult,
    RepairObservation,
    RepairProposal,
    run_repair_loop,
)


def _proposal(observation, value="2"):
    return RepairProposal("change the unstable input", ({"value": value},), observation.digest)


def test_success_records_hypothesis_evidence_and_transaction(tmp_path):
    initial = RepairObservation({"code": "diverged", "residual": 10})
    outcome = run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(3),
        propose=_proposal,
        execute_candidate=lambda proposal: RepairExperimentResult(
            "succeeded", RepairObservation({"code": "ok"}), "tx-1",
        ),
    )
    record = json.loads(outcome.journal_path.read_text())
    assert (outcome.status, outcome.executions) == ("succeeded", 1)
    assert record["experiments"][0]["observation_digest"] == initial.digest
    assert record["experiments"][0]["transaction_id"] == "tx-1"


def test_execution_budget_bounds_candidates_not_hypotheses(tmp_path):
    observation = RepairObservation({"code": "failed"})
    outcome = run_repair_loop(
        observation, output_dir=tmp_path, budgets=RepairBudgets(2, max_unchanged_failures=9),
        propose=lambda current: _proposal(current),
        execute_candidate=lambda proposal: RepairExperimentResult("failed", observation),
    )
    assert (outcome.reason, outcome.executions) == ("execution_budget_exhausted", 2)


def test_repeated_unchanged_failure_stops_before_budget(tmp_path):
    observation = RepairObservation({"code": "same"})
    outcome = run_repair_loop(
        observation, output_dir=tmp_path, budgets=RepairBudgets(10, max_unchanged_failures=2),
        propose=lambda current: _proposal(current),
        execute_candidate=lambda proposal: RepairExperimentResult("failed", observation),
    )
    assert (outcome.reason, outcome.executions, outcome.unchanged_failures) == (
        "repeated_unchanged_failure", 2, 2,
    )


def test_changed_failure_resets_unchanged_counter(tmp_path):
    observations = iter([
        RepairObservation({"code": "b"}),
        RepairObservation({"code": "b"}),
        RepairObservation({"code": "c"}),
    ])
    outcome = run_repair_loop(
        RepairObservation({"code": "a"}), output_dir=tmp_path,
        budgets=RepairBudgets(3, max_unchanged_failures=2),
        propose=lambda current: _proposal(current),
        execute_candidate=lambda proposal: RepairExperimentResult("failed", next(observations)),
    )
    assert outcome.reason == "execution_budget_exhausted"
    assert outcome.unchanged_failures == 0


def test_elapsed_budget_is_checked_before_reserving_execution(tmp_path):
    ticks = iter([0.0, 5.0])
    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(3, max_elapsed_seconds=4),
        propose=lambda observation: pytest.fail("proposal should not be requested"),
        execute_candidate=lambda proposal: pytest.fail("candidate should not run"),
        monotonic=lambda: next(ticks),
    )
    assert (outcome.reason, outcome.executions) == ("elapsed_budget_exhausted", 0)


def test_slow_proposal_cannot_start_candidate_after_elapsed_budget(tmp_path):
    ticks = iter([0.0, 1.0, 5.0])
    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(3, max_elapsed_seconds=4),
        propose=_proposal,
        execute_candidate=lambda proposal: pytest.fail("candidate should not run"),
        monotonic=lambda: next(ticks),
    )
    assert (outcome.reason, outcome.executions) == ("elapsed_budget_exhausted", 0)


def test_stale_proposal_is_rejected_before_execution(tmp_path):
    with pytest.raises(ValueError, match="stale observation"):
        run_repair_loop(
            RepairObservation({"code": "new"}), output_dir=tmp_path,
            budgets=RepairBudgets(1),
            propose=lambda observation: RepairProposal("idea", (), "sha256:stale"),
            execute_candidate=lambda proposal: pytest.fail("candidate should not run"),
        )
    record = json.loads(next((tmp_path / "repair_loops").iterdir()).read_text())
    assert (record["status"], record["reason"]) == (
        "failed", "proposer_contract_error",
    )


def test_executor_error_consumes_durable_reserved_slot(tmp_path):
    def crash(proposal):
        raise RuntimeError("executor crashed")

    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(3), propose=_proposal, execute_candidate=crash,
    )
    record = json.loads(outcome.journal_path.read_text())
    assert (outcome.status, outcome.reason, outcome.executions) == (
        "failed", "candidate_executor_error", 1,
    )
    assert record["experiments"][0]["status"] == "error"


def test_separate_loops_keep_separate_durable_histories(tmp_path):
    kwargs = dict(
        output_dir=tmp_path,
        budgets=RepairBudgets(1),
        propose=lambda observation: None,
        execute_candidate=lambda proposal: pytest.fail("candidate should not run"),
    )
    first = run_repair_loop(RepairObservation({"run": 1}), **kwargs)
    second = run_repair_loop(RepairObservation({"run": 2}), **kwargs)

    assert first.journal_path != second.journal_path
    assert first.journal_path.exists() and second.journal_path.exists()
