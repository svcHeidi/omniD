"""Structured, solver-neutral execution of one validated repair candidate."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from .attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from .execution_context import StepExecutionContext
from .failure_context import build_failure_context
from .launch_readiness import is_execution_successful
from .remediation import build_candidate_remediations
from .remediation_audit import append_remediation_record
from .remediation_transaction import (
    RemediationTransactionError,
    baseline_is_restored,
    begin_remediation_transaction,
    finish_remediation_transaction,
    mark_remediation_dispatching,
    record_remediation_outcome,
    require_reusable_case,
)
from .repair_loop import (
    RepairExperimentResult,
    RepairObservation,
    RepairProposal,
    RepairReservation,
    claim_repair_reservation,
    complete_repair_reservation,
)
from .resume import validate_resume
from .workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME
from .workflow_runner import WorkflowStepRunResult, _step_state_by_id, run_workflow_step
from .workflow_state import workflow_digest, workflow_state_from_json


@dataclass(frozen=True)
class StepCandidateResult:
    status: Literal["succeeded", "failed", "rejected"]
    payload: Mapping[str, Any]
    transaction_id: str | None
    dispatched: bool


def execute_repair_candidate(
    context: StepExecutionContext,
    *,
    step_id: str,
    proposal: RepairProposal,
    reservation: RepairReservation,
    reobserve: Callable[[], RepairObservation],
    tail_lines: int = 200,
    run_step: Callable[..., WorkflowStepRunResult] = run_workflow_step,
) -> StepCandidateResult:
    """Acquire execution ownership and execute one durably reserved proposal."""
    with acquire_case_lease(context.case_root):
        with acquire_attempt_lease(context.output_dir):
            if proposal.digest != reservation.proposal_digest:
                raise ValueError("repair proposal does not match its reserved digest")
            if proposal.based_on_observation_digest != reservation.observation_digest:
                raise ValueError("repair proposal observation does not match its reservation")
            claim_repair_reservation(
                context.output_dir, reservation, case_root=context.case_root,
            )
            result = execute_step_candidate_owned(
                context,
                step_id=step_id,
                overrides=list(proposal.overrides),
                hypothesis=proposal.hypothesis,
                reservation=reservation,
                proposal=proposal,
                reobserve=reobserve,
                tail_lines=tail_lines,
                run_step=run_step,
            )
            _validate_repair_result(result, reservation)
            evidence = result.payload.get("repair_observation")
            if not isinstance(evidence, Mapping):
                raise ValueError("repair candidate did not return a structured observation")
            complete_repair_reservation(
                context.output_dir,
                reservation,
                status=result.status,
                observation=RepairObservation(evidence),
                transaction_id=result.transaction_id,
            )
            return result


def repair_experiment_result(
    result: StepCandidateResult,
    reservation: RepairReservation,
) -> RepairExperimentResult:
    """Adapt a bound structured execution result to the repair-loop contract."""
    _validate_repair_result(result, reservation)
    evidence = result.payload.get("repair_observation")
    if not isinstance(evidence, Mapping):
        raise ValueError("repair candidate did not return a structured observation")
    return RepairExperimentResult(
        result.status,
        RepairObservation(evidence),
        loop_id=reservation.loop_id,
        execution=reservation.execution,
        reservation_id=reservation.reservation_id,
        observation_digest=reservation.observation_digest,
        proposal_digest=reservation.proposal_digest,
        transaction_id=result.transaction_id,
    )


def execute_step_candidate_owned(
    context: StepExecutionContext,
    *,
    step_id: str,
    overrides: list[dict[str, Any]] | None = None,
    hypothesis: str | None = None,
    reservation: RepairReservation | None = None,
    proposal: RepairProposal | None = None,
    reobserve: Callable[[], RepairObservation] | None = None,
    tail_lines: int = 200,
    run_step: Callable[..., WorkflowStepRunResult] = run_workflow_step,
) -> StepCandidateResult:
    """Validate, mutate, replan and dispatch while both leases are held."""
    case_root = Path(context.case_root)
    output_dir = Path(context.output_dir)
    if not case_lease_is_held(case_root) or not attempt_lease_is_held(output_dir):
        raise RemediationTransactionError(
            "step candidate execution requires owned case and output leases"
        )
    require_reusable_case(case_root, explicit_repair=overrides is not None)

    current_observation: RepairObservation | None = None
    repair_binding: Mapping[str, Any] | None = None
    if reservation is not None:
        if proposal is None or reobserve is None:
            raise ValueError("reserved repair execution requires proposal and re-observation")
        if proposal.digest != reservation.proposal_digest:
            raise ValueError("repair proposal does not match its reserved digest")
        if proposal.based_on_observation_digest != reservation.observation_digest:
            raise ValueError("repair proposal observation does not match its reservation")
        current_observation = reobserve()
        if current_observation.digest != reservation.observation_digest:
            return StepCandidateResult(
                "rejected",
                {
                    "status": "failed",
                    "entry": context.entry_label,
                    "step": step_id,
                    "error": "repair proposal is based on stale execution evidence",
                    "repair_observation": current_observation.evidence,
                    "repair_observation_digest": current_observation.digest,
                },
                None,
                False,
            )
        repair_binding = asdict(reservation)

    state_path = output_dir / STATE_FILENAME
    workflow_state = context.planned_state
    if state_path.exists():
        workflow_state = workflow_state_from_json(json.loads(state_path.read_text()))
        validate_resume(
            workflow_state,
            context.workflow_dag,
            case_root=case_root,
            driver_context=context.driver_context,
            env=context.execution_env,
            expected_artifacts=tuple(context.expected_artifacts or ()),
        )

    workflow_dag = context.workflow_dag
    expected_artifacts = context.expected_artifacts
    transaction: dict[str, Any] | None = None
    effective_resolution: tuple[dict[str, Any], ...] = ()
    mutation_applied = False
    if overrides is not None:
        if context.driver_context is None:
            raise ValueError("candidate execution requires a driver context")
        try:
            transaction = begin_remediation_transaction(
                case_root,
                output_dir=output_dir,
                step_id=step_id,
                overrides=overrides,
                hypothesis=hypothesis,
                target_paths=context.driver_context.capabilities.override_scopes.target_paths(
                    overrides,
                    case_root=case_root,
                    driver_context=context.driver_context,
                ),
                repair_binding=repair_binding,
            )
            effective_resolution = (
                context.driver_context.capabilities.override_scopes.apply(
                    overrides,
                    case_root=case_root,
                    driver_context=context.driver_context,
                    execution_env=context.execution_env,
                )
                or ()
            )
            mutation_applied = True
            unresolved = tuple(
                item
                for item in effective_resolution
                if item.get("status") != "resolved"
                or item.get("matches_requested") is False
            )
            if unresolved:
                detail = "; ".join(
                    f"{item.get('driver_path')}: "
                    f"{item.get('message') or ('effective value differs from request' if item.get('matches_requested') is False else item.get('status'))}"
                    for item in unresolved
                )
                raise ValueError(f"effective dictionary resolution failed: {detail}")
            if context.replan_after_mutation is None:
                raise ValueError("candidate execution has no plan reconstruction contract")
            replanned = context.replan_after_mutation()
            if workflow_digest(replanned.workflow_dag) != workflow_digest(workflow_dag):
                raise ValueError(
                    "applied overrides changed the workflow plan; start a fresh run "
                    "from the replanned entry/document instead of rerunning one step"
                )
            workflow_dag = replanned.workflow_dag
            expected_artifacts = replanned.expected_artifacts
            if not state_path.exists():
                workflow_state = replanned.planned_state
            transaction = finish_remediation_transaction(
                case_root,
                transaction,
                status="validated",
                effective_resolution=effective_resolution,
                plan_digest=workflow_digest(workflow_dag),
            )
        except (OSError, ValueError) as exc:
            repair_result = None
            if reobserve is not None:
                current_observation = reobserve()
                repair_result = _repair_result_payload("rejected", current_observation)
            if transaction is not None:
                restored = baseline_is_restored(
                    case_root, transaction, output_dir=output_dir,
                )
                transaction = finish_remediation_transaction(
                    case_root,
                    transaction,
                    status="rolled_back" if restored else "rejected",
                    effective_resolution=effective_resolution,
                    error=str(exc),
                    repair_result=repair_result,
                )
            if mutation_applied:
                append_remediation_record(
                    output_dir,
                    step_id=step_id,
                    attempt=_step_state_by_id(workflow_state, step_id).attempt,
                    applied_overrides=overrides,
                    resulting_status="replan_error",
                    effective_resolution=effective_resolution,
                )
            payload = {
                "status": "failed",
                "entry": context.entry_label,
                "step": step_id,
                "error": f"candidate rejected: {exc}",
            }
            _attach_transaction(payload, transaction)
            if current_observation is not None:
                payload["repair_observation"] = current_observation.evidence
                payload["repair_observation_digest"] = current_observation.digest
            return StepCandidateResult(
                "rejected", payload, _transaction_id(transaction), False,
            )

    if transaction is not None:
        transaction = mark_remediation_dispatching(case_root, transaction)
    try:
        run_result = run_step(
            workflow_dag,
            workflow_state,
            step_id,
            case_root=case_root,
            log_dir=output_dir / WORKFLOW_LOGS_DIRNAME,
            state_path=state_path,
            expected_artifacts=expected_artifacts,
            env=context.execution_env,
            driver_context=context.driver_context,
            leases_held=True,
        )
    except Exception as exc:
        if reservation is not None:
            # A repair-loop executor crash is not scientific evidence. Keep
            # the durable transaction in dispatching so recovery can identify
            # the interrupted candidate, and let the loop record executor_error.
            raise
        if transaction is not None:
            transaction = record_remediation_outcome(
                case_root,
                transaction,
                execution_status="error",
                attempt=_attempt(workflow_state, step_id),
            )
        if overrides is not None:
            append_remediation_record(
                output_dir,
                step_id=step_id,
                attempt=_attempt(workflow_state, step_id),
                applied_overrides=overrides,
                resulting_status="rerun_error",
                effective_resolution=effective_resolution,
            )
        payload = {
            "status": "failed",
            "entry": context.entry_label,
            "step": step_id,
            "error": str(exc),
            "workflow_state": workflow_state.to_json(),
        }
        _attach_transaction(payload, transaction)
        if reobserve is not None:
            current_observation = reobserve()
            payload["repair_observation"] = current_observation.evidence
            payload["repair_observation_digest"] = current_observation.digest
        return StepCandidateResult("failed", payload, _transaction_id(transaction), True)

    step_state = _step_state_by_id(run_result.state, step_id)
    successful = is_execution_successful(step_state.status)
    cli_status = "ok" if successful else "failed"
    payload = {
        "status": cli_status,
        "entry": context.entry_label,
        "step": step_id,
        "exit_code": run_result.exit_code,
        "stdout_log": run_result.stdout_log,
        "stderr_log": run_result.stderr_log,
        "workflow_state_path": str(state_path),
        "workflow_state": run_result.state.to_json(),
    }
    if not successful:
        failure = build_failure_context(step_state, max_lines=tail_lines)
        failure["candidate_remediations"] = [
            hint.to_json() for hint in build_candidate_remediations(failure)
        ]
        payload["failure_context"] = failure
    if reobserve is not None:
        current_observation = reobserve()
        payload["repair_observation"] = current_observation.evidence
        payload["repair_observation_digest"] = current_observation.digest
    if overrides is not None:
        if transaction is not None:
            transaction = record_remediation_outcome(
                case_root,
                transaction,
                execution_status=cli_status,
                attempt=step_state.attempt,
                repair_result=(
                    _repair_result_payload(
                        "succeeded" if successful else "failed",
                        current_observation,
                    )
                    if current_observation is not None else None
                ),
            )
        append_remediation_record(
            output_dir,
            step_id=step_id,
            attempt=step_state.attempt,
            applied_overrides=overrides,
            resulting_status=cli_status,
            effective_resolution=effective_resolution,
        )
        payload["effective_dictionary_resolution"] = list(effective_resolution)
        _attach_transaction(payload, transaction)
    return StepCandidateResult(
        "succeeded" if successful else "failed",
        payload,
        _transaction_id(transaction),
        True,
    )


def _attempt(state: object, step_id: str) -> int:
    try:
        return int(_step_state_by_id(state, step_id).attempt)
    except Exception:
        return 0


def _repair_result_payload(
    status: str, observation: RepairObservation,
) -> dict[str, Any]:
    return {
        "status": status,
        "observation": observation.evidence,
        "observation_digest": observation.digest,
    }


def _transaction_id(transaction: Mapping[str, Any] | None) -> str | None:
    return str(transaction["transaction_id"]) if transaction is not None else None


def _attach_transaction(
    payload: dict[str, Any], transaction: Mapping[str, Any] | None,
) -> None:
    if transaction is None:
        return
    payload["remediation_transaction"] = {
        key: transaction.get(key)
        for key in (
            "transaction_id", "origin", "status", "hypothesis", "proposal_digest",
            "plan_digest", "parent_transaction_id", "repeats_failed_proposal",
            "candidate_archive", "execution_status", "execution_attempt",
            "repair_binding",
        )
        if key in transaction
    }


def _validate_repair_result(
    result: StepCandidateResult,
    reservation: RepairReservation,
) -> None:
    transaction = result.payload.get("remediation_transaction")
    if result.transaction_id is None:
        if result.status != "rejected" or result.dispatched:
            raise RemediationTransactionError(
                "a bound repair result without a transaction must be a pre-mutation rejection"
            )
        return
    if not isinstance(transaction, Mapping):
        raise RemediationTransactionError("bound repair result omitted its transaction")
    if transaction.get("transaction_id") != result.transaction_id:
        raise RemediationTransactionError("repair result transaction identity mismatch")
    if transaction.get("repair_binding") != asdict(reservation):
        raise RemediationTransactionError("repair result reservation binding mismatch")
    expected_statuses = {
        "succeeded": {"accepted"},
        "failed": {"rejected"},
        "rejected": {"rejected", "rolled_back"},
    }[result.status]
    if transaction.get("status") not in expected_statuses:
        raise RemediationTransactionError(
            "repair result does not match the terminal transaction status"
        )
    if result.status == "succeeded" and not result.dispatched:
        raise RemediationTransactionError("successful repair result was not dispatched")
    if result.status == "failed" and not result.dispatched:
        raise RemediationTransactionError("failed repair result was not dispatched")
