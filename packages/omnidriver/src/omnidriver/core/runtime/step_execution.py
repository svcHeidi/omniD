"""Structured, solver-neutral execution of one step, optionally after a case edit."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from .attempt_lease import attempt_lease_is_held, case_lease_is_held
from .execution_context import ReplannedExecution, StepExecutionContext
from .failure_context import build_failure_context
from .launch_readiness import is_execution_successful
from .remediation import build_candidate_remediations
from .remediation_audit import append_remediation_record
from .resume import checkpoint_snapshot, validate_resume
from .transaction_mechanics import atomic_write_json
from .workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME
from .workflow_runner import (
    WorkflowStepRunResult, _step_state_by_id, check_step_runnable, run_workflow_step, settle_interrupted_steps,
)
from .workflow_state import workflow_digest, workflow_state_from_json
from ..case_transaction import CaseTransactionError


@dataclass(frozen=True)
class StepResult:
    status: Literal["succeeded", "failed", "rejected"]
    payload: Mapping[str, Any]


def execute_step_owned(
    context: StepExecutionContext,
    *,
    step_id: str,
    study: Mapping[str, Any] | None = None,
    tail_lines: int = 200,
    run_step: Callable[..., WorkflowStepRunResult] = run_workflow_step,
) -> StepResult:
    """Run one step while both leases are held, first editing the case with
    ``study`` (``document:key`` patches) when one is given.

    A step that cannot run is refused before the case is touched. The edit
    commits through the case writer, which rolls back its own
    failure, and which the stack's rules can refuse the same way, leaving the
    case as it was, as does a replan whose workflow changed. Patches that
    change nothing neither rerun a step that has run nor spend an attempt
    (status ``unchanged``, and the result is a failure: the step still is).
    """
    case_root = Path(context.case_root)
    output_dir = Path(context.output_dir)
    if not case_lease_is_held(case_root) or not attempt_lease_is_held(output_dir):
        raise RuntimeError("step execution requires owned case and output leases")

    state_path = output_dir / STATE_FILENAME
    workflow_state = context.planned_state
    if state_path.exists():
        workflow_state = settle_interrupted_steps(
            workflow_state_from_json(json.loads(state_path.read_text())), state_path,
        )
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
    applied: tuple[dict[str, Any], ...] = ()
    if study is not None:
        check_step_runnable(workflow_dag, workflow_state, step_id)
        replanned: list[ReplannedExecution] = []

        def check_the_plan() -> None:
            """Runs inside the edit's transaction: a plan that changed rolls the edit back."""
            candidate = context.replan_after_mutation()
            if workflow_digest(candidate.workflow_dag) != workflow_digest(workflow_dag):
                raise ValueError(
                    "the patches changed the workflow plan; plan again with them instead of "
                    "rerunning one step. The case is as it was before the edit"
                )
            replanned.append(candidate)

        try:
            if context.apply_study is None or context.replan_after_mutation is None:
                raise ValueError("this plan has no tutorial record whose case can be edited")
            applied = context.apply_study(study, check_the_plan)
            step_state = _step_state_by_id(workflow_state, step_id)
            if all(patch["status"] == "unchanged" for patch in applied) and (
                step_state.attempt > 0 or step_state.status != "pending"
            ):
                # Nothing changed, so another run would end as the last did.
                return StepResult("failed", {
                    "status": "unchanged",
                    "entry": context.entry_label,
                    "step": step_id,
                    "message": "no patch changed the case, so the step was not rerun and no attempt was spent",
                    "applied_patches": list(applied),
                    "workflow_state": workflow_state.to_json(),
                })
            if replanned:
                workflow_dag = replanned[0].workflow_dag
                expected_artifacts = replanned[0].expected_artifacts
            if state_path.exists() and context.driver_context is not None and replanned:
                # The edit is deliberate and passed its checks, so the saved
                # evidence follows it: a later edit must not be refused for this one.
                workflow_state = replace(workflow_state, resume_snapshot=checkpoint_snapshot(
                    case_root, workflow_dag, context.driver_context, context.execution_env,
                ))
                atomic_write_json(state_path, workflow_state.to_json())
            if not state_path.exists() and replanned:
                workflow_state = replanned[0].planned_state
        except (OSError, ValueError, CaseTransactionError) as exc:
            return StepResult("rejected", {
                "status": "failed",
                "entry": context.entry_label,
                "step": step_id,
                "error": f"candidate rejected: {exc}",
            })

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
        if study is not None:
            append_remediation_record(
                output_dir, step_id=step_id, attempt=_attempt(workflow_state, step_id),
                applied_patches=list(applied), resulting_status="rerun_error",
            )
        return StepResult("failed", {
            "status": "failed",
            "entry": context.entry_label,
            "step": step_id,
            "error": str(exc),
            "workflow_state": workflow_state.to_json(),
        })

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
    if study is not None:
        append_remediation_record(
            output_dir, step_id=step_id, attempt=step_state.attempt,
            applied_patches=list(applied), resulting_status=cli_status,
        )
        payload["applied_patches"] = list(applied)
    return StepResult("succeeded" if successful else "failed", payload)


def _attempt(state: object, step_id: str) -> int:
    try:
        return int(_step_state_by_id(state, step_id).attempt)
    except Exception:
        return 0
