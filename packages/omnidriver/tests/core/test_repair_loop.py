from __future__ import annotations

import json
import shutil
import threading
import uuid

import pytest

from omnidriver.core.runtime.repair_loop import (
    RepairBudgets,
    RepairExperimentResult,
    RepairObservation,
    RepairProposal,
    RepairReservation,
    observation_from_failure_context,
    run_repair_loop,
)


def _proposal(observation, value="2"):
    return RepairProposal("change the unstable input", ({"value": value},), observation.digest)


def _result(status, observation, reservation, transaction_id=None):
    return RepairExperimentResult(
        status,
        observation,
        loop_id=reservation.loop_id,
        execution=reservation.execution,
        reservation_id=reservation.reservation_id,
        observation_digest=reservation.observation_digest,
        proposal_digest=reservation.proposal_digest,
        transaction_id=transaction_id,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"loop_id": "not-a-uuid"},
        {"execution": 0},
        {"execution": True},
        {"reservation_id": str(uuid.uuid4()).upper()},
        {"observation_digest": "sha256:short"},
        {"proposal_digest": "sha256:" + "G" * 64},
    ],
)
def test_repair_reservation_validates_before_execution(changes):
    values = {
        "loop_id": str(uuid.uuid4()),
        "execution": 1,
        "reservation_id": str(uuid.uuid4()),
        "observation_digest": "sha256:" + "a" * 64,
        "proposal_digest": "sha256:" + "b" * 64,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        RepairReservation(**values)


def test_success_records_hypothesis_evidence_and_transaction(tmp_path):
    initial = RepairObservation({"code": "diverged", "residual": 10})
    outcome = run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(3),
        propose=_proposal,
        execute_candidate=lambda proposal, reservation: _result(
            "succeeded", RepairObservation({"code": "ok"}), reservation, "tx-1",
        ),
    )
    record = json.loads(outcome.journal_path.read_text())
    assert (outcome.status, outcome.executions) == ("succeeded", 1)
    assert record["experiments"][0]["observation_digest"] == initial.digest
    assert record["initial_observation"] == {"code": "diverged", "residual": 10}
    assert record["experiments"][0]["resulting_observation"] == {"code": "ok"}
    assert record["experiments"][0]["transaction_id"] == "tx-1"
    assert record["experiments"][0]["reservation_id"]


def test_executor_receives_immutable_persisted_reservation(tmp_path):
    received = []

    def execute(proposal, reservation):
        del proposal
        received.append(reservation)
        with pytest.raises(AttributeError):
            reservation.execution = 2
        return _result("succeeded", RepairObservation({"code": "ok"}), reservation)

    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(1), propose=_proposal, execute_candidate=execute,
    )

    record = json.loads(outcome.journal_path.read_text())
    assert isinstance(received[0], RepairReservation)
    assert record["experiments"][0]["reservation_id"] == received[0].reservation_id


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("loop_id", "wrong-loop"),
        ("execution", 999),
        ("reservation_id", "wrong-reservation"),
        ("observation_digest", "sha256:wrong-observation"),
        ("proposal_digest", "sha256:wrong-proposal"),
    ],
)
def test_candidate_result_must_match_its_reservation(
    tmp_path, field, replacement,
):
    loop_id = str(uuid.uuid4())

    def execute(proposal, reservation):
        del proposal
        binding = {
            "loop_id": reservation.loop_id,
            "execution": reservation.execution,
            "reservation_id": reservation.reservation_id,
            "observation_digest": reservation.observation_digest,
            "proposal_digest": reservation.proposal_digest,
        }
        binding[field] = replacement
        return RepairExperimentResult(
            "succeeded", RepairObservation({"code": "ok"}), **binding,
        )

    with pytest.raises(ValueError, match=field):
        run_repair_loop(
            RepairObservation({"code": "failed"}), output_dir=tmp_path,
            budgets=RepairBudgets(1), propose=_proposal, execute_candidate=execute,
            loop_id=loop_id,
        )

    control = tmp_path.parent / ".omnidriver-repair-control"
    journals = tuple(control.rglob(f"{loop_id}.json"))
    assert len(journals) == 1
    record = json.loads(journals[0].read_text())
    assert (record["status"], record["reason"], record["executions"]) == (
        "failed", "candidate_result_contract_error", 1,
    )
    assert record["experiments"][0]["status"] == "error"


def test_execution_budget_bounds_candidates_not_hypotheses(tmp_path):
    observation = RepairObservation({"code": "failed"})
    outcome = run_repair_loop(
        observation, output_dir=tmp_path, budgets=RepairBudgets(2, max_unchanged_failures=9),
        propose=lambda current: _proposal(current),
        execute_candidate=lambda proposal, reservation: _result(
            "failed", observation, reservation,
        ),
    )
    assert (outcome.reason, outcome.executions) == ("execution_budget_exhausted", 2)


def test_repeated_unchanged_failure_stops_before_budget(tmp_path):
    observation = RepairObservation({"code": "same"})
    outcome = run_repair_loop(
        observation, output_dir=tmp_path, budgets=RepairBudgets(10, max_unchanged_failures=2),
        propose=lambda current: _proposal(current),
        execute_candidate=lambda proposal, reservation: _result(
            "failed", observation, reservation,
        ),
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
        execute_candidate=lambda proposal, reservation: _result(
            "failed", next(observations), reservation,
        ),
    )
    assert outcome.reason == "execution_budget_exhausted"
    assert outcome.unchanged_failures == 0


def test_elapsed_budget_is_checked_before_reserving_execution(tmp_path):
    ticks = iter([0.0, 5.0])
    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(3, max_elapsed_seconds=4),
        propose=lambda observation: pytest.fail("proposal should not be requested"),
        execute_candidate=lambda proposal, reservation: pytest.fail(
            "candidate should not run"
        ),
        monotonic=lambda: next(ticks),
    )
    assert (outcome.reason, outcome.executions) == ("elapsed_budget_exhausted", 0)


def test_slow_proposal_cannot_start_candidate_after_elapsed_budget(tmp_path):
    ticks = iter([0.0, 1.0, 5.0])
    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=tmp_path,
        budgets=RepairBudgets(3, max_elapsed_seconds=4),
        propose=_proposal,
        execute_candidate=lambda proposal, reservation: pytest.fail(
            "candidate should not run"
        ),
        monotonic=lambda: next(ticks),
    )
    assert (outcome.reason, outcome.executions) == ("elapsed_budget_exhausted", 0)


def test_stale_proposal_is_rejected_before_execution(tmp_path):
    loop_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="stale observation"):
        run_repair_loop(
            RepairObservation({"code": "new"}), output_dir=tmp_path,
            budgets=RepairBudgets(1),
            propose=lambda observation: RepairProposal("idea", (), "sha256:stale"),
            execute_candidate=lambda proposal, reservation: pytest.fail(
                "candidate should not run"
            ),
            loop_id=loop_id,
        )
    matches = list((tmp_path.parent / ".omnidriver-repair-control").rglob(f"{loop_id}.json"))
    assert len(matches) == 1
    record = json.loads(matches[0].read_text())
    assert (record["status"], record["reason"]) == (
        "failed", "proposer_contract_error",
    )


def test_executor_error_consumes_durable_reserved_slot(tmp_path):
    def crash(proposal, reservation):
        del proposal, reservation
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
        execute_candidate=lambda proposal, reservation: pytest.fail(
            "candidate should not run"
        ),
    )
    first = run_repair_loop(RepairObservation({"run": 1}), **kwargs)
    second = run_repair_loop(RepairObservation({"run": 2}), **kwargs)

    assert first.journal_path != second.journal_path
    assert first.journal_path.exists() and second.journal_path.exists()


def test_observation_and_proposal_are_deep_copied_at_the_boundary():
    evidence = {"diagnostics": [{"code": "diverged"}]}
    overrides = ({"value": {"nested": [1]}},)
    observation = RepairObservation(evidence)
    proposal = RepairProposal("idea", overrides, observation.digest)

    evidence["diagnostics"][0]["code"] = "mutated"
    overrides[0]["value"]["nested"].append(2)

    assert observation.evidence == {"diagnostics": [{"code": "diverged"}]}
    assert proposal.overrides == ({"value": {"nested": [1]}},)


def test_non_json_evidence_and_non_finite_numbers_are_rejected():
    with pytest.raises(ValueError, match="strict JSON"):
        RepairObservation({"bad": object()})
    with pytest.raises(ValueError, match="strict JSON"):
        RepairObservation({"bad": float("nan")})


def test_failure_observation_ignores_attempt_and_log_locations():
    base = {
        "step_id": "solve", "exit_code": 1,
        "diagnostics": [{"code": "diverged"}],
        "stdout_tail": "same", "stderr_tail": "same",
        "stdout_truncated": False, "stderr_truncated": False,
    }
    first = observation_from_failure_context({
        **base, "attempt": 1, "stdout_log": "/run/1.out", "stderr_log": "/run/1.err",
    })
    second = observation_from_failure_context({
        **base, "attempt": 9, "stdout_log": "/run/9.out", "stderr_log": "/run/9.err",
    })

    assert first.digest == second.digest
    assert "attempt" not in first.evidence


def test_restart_same_loop_id_accounts_for_crashed_reserved_candidate(tmp_path):
    loop_id = str(uuid.uuid4())
    initial = RepairObservation({"code": "failed"})

    with pytest.raises(KeyboardInterrupt):
        run_repair_loop(
            initial, output_dir=tmp_path, budgets=RepairBudgets(3),
            propose=_proposal,
            execute_candidate=lambda proposal, reservation: (
                _ for _ in ()
            ).throw(KeyboardInterrupt()),
            loop_id=loop_id,
        )

    outcome = run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(3),
        propose=lambda observation: pytest.fail("must recover before proposing again"),
        execute_candidate=lambda proposal, reservation: pytest.fail(
            "must not execute again"
        ),
        loop_id=loop_id,
    )

    assert (outcome.status, outcome.reason, outcome.executions) == (
        "failed", "interrupted_candidate_requires_recovery", 1,
    )
    record = json.loads(outcome.journal_path.read_text())
    assert record["experiments"][0]["status"] == "interrupted"


def test_finished_loop_id_is_idempotent(tmp_path):
    loop_id = str(uuid.uuid4())
    initial = RepairObservation({"code": "failed"})
    first = run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(1),
        propose=lambda observation: None,
        execute_candidate=lambda proposal, reservation: pytest.fail("must not execute"),
        loop_id=loop_id,
    )
    second = run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(1),
        propose=lambda observation: pytest.fail("finished loop must not propose"),
        execute_candidate=lambda proposal, reservation: pytest.fail(
            "finished loop must not execute"
        ),
        loop_id=loop_id,
    )

    assert second == first


def test_same_loop_cannot_be_reopened_concurrently(tmp_path):
    loop_id = str(uuid.uuid4())
    initial = RepairObservation({"code": "failed"})
    entered = threading.Event()
    release = threading.Event()

    def execute(proposal, reservation):
        del proposal
        entered.set()
        assert release.wait(timeout=2)
        return _result("succeeded", RepairObservation({"code": "ok"}), reservation)

    thread = threading.Thread(target=lambda: run_repair_loop(
        initial, output_dir=tmp_path, budgets=RepairBudgets(1),
        propose=_proposal, execute_candidate=execute, loop_id=loop_id,
    ))
    thread.start()
    assert entered.wait(timeout=2)
    try:
        with pytest.raises(RuntimeError, match="already owned"):
            run_repair_loop(
                initial, output_dir=tmp_path, budgets=RepairBudgets(1),
                propose=_proposal,
                execute_candidate=lambda proposal, reservation: pytest.fail(
                    "must not execute"
                ),
                loop_id=loop_id,
            )
    finally:
        release.set()
        thread.join(timeout=2)
    assert not thread.is_alive()


def test_journal_control_path_is_outside_fresh_cleaned_output(tmp_path):
    output_dir = tmp_path / "output"
    outcome = run_repair_loop(
        RepairObservation({"code": "failed"}), output_dir=output_dir,
        budgets=RepairBudgets(1), propose=lambda observation: None,
        execute_candidate=lambda proposal, reservation: pytest.fail("must not execute"),
    )

    assert not outcome.journal_path.is_relative_to(output_dir)
    assert outcome.journal_path.is_relative_to(output_dir.parent)


def test_legacy_output_journal_is_migrated_without_resetting_loop(tmp_path):
    output_dir = tmp_path / "output"
    loop_id = str(uuid.uuid4())
    initial = RepairObservation({"code": "failed"})
    first = run_repair_loop(
        initial, output_dir=output_dir, budgets=RepairBudgets(1),
        propose=lambda observation: None,
        execute_candidate=lambda proposal, reservation: pytest.fail("must not execute"),
        loop_id=loop_id,
    )
    legacy = output_dir / "repair_loops" / f"{loop_id}.json"
    legacy.parent.mkdir(parents=True)
    shutil.move(first.journal_path, legacy)

    second = run_repair_loop(
        initial, output_dir=output_dir, budgets=RepairBudgets(1),
        propose=lambda observation: pytest.fail("completed loop must not restart"),
        execute_candidate=lambda proposal, reservation: pytest.fail("must not execute"),
        loop_id=loop_id,
    )

    assert second.reason == "proposer_stopped"
    assert second.journal_path.exists()
