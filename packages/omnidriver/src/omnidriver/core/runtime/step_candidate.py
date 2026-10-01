"""Structured, solver-neutral execution of one step, optionally under a configuration patch."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from .attempt_lease import attempt_lease_is_held, case_lease_is_held
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


def execute_step_candidate_owned(
    context: StepExecutionContext,
    *,
    step_id: str,
    overrides: list[dict[str, Any]] | None = None,
    hypothesis: str | None = None,
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
    if overrides is not None:
        if transaction is not None:
            transaction = record_remediation_outcome(
                case_root,
                transaction,
                execution_status=cli_status,
                attempt=step_state.attempt,
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
            "transaction_id", "status", "hypothesis", "proposal_digest",
            "plan_digest", "parent_transaction_id", "repeats_failed_proposal",
            "candidate_archive", "execution_status", "execution_attempt",
        )
        if key in transaction
    }
