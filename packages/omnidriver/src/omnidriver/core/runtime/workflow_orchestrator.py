from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .failure_classification import classify_failure
from .attempt_lease import (
    AttemptLeaseError,
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from .workflow_runner import _atomic_write_json, _step_by_id, _step_state_by_id, run_workflow_step
from .workflow_state import WorkflowRunState, WorkflowStepState, replace_step_state


if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


#: The workflow-state record's filename, named once here (final review M6,
#: 2026-09-26) instead of restated as a literal at each write/read site
#: (``cli.py``, ``postprocess_phase.py``, ``step_candidate.py``,
#: ``sweep_runner.py``, ``execution_context.py``, ``run_discovery.py``,
#: ``runtime_records.CORE_RUNTIME_RECORDS`` and ``fresh._OMNIDRIVER_MARKER_NAMES``).
STATE_FILENAME = "workflow_state.json"

#: The per-run step-log directory's name, named once here for the same
#: reason (used by ``step_candidate.py`` and ``runtime_records.py``).
WORKFLOW_LOGS_DIRNAME = "workflow_logs"


@dataclass(frozen=True)
class WorkflowRunOutcome:
    state: WorkflowRunState
    steps: tuple[dict[str, Any], ...]


def backoff_delay(attempt: int, backoff_seconds: float, *, cap_seconds: float = 60.0) -> float:
    """Exponential backoff for the (1-based) attempt that just failed, capped."""
    return min(backoff_seconds * (2 ** (attempt - 1)), cap_seconds)


def _resolve_policy(step: dict[str, Any], default_max_attempts: int) -> tuple[int, float, bool]:
    policy = step.get("retry_policy") or {}
    safe_to_retry = policy.get("safe_to_retry") is True
    return (
        policy.get("max_attempts", default_max_attempts if safe_to_retry else 1),
        policy.get("backoff_seconds", 0),
        safe_to_retry,
    )


def run_workflow(
    workflow_dag: dict[str, Any],
    workflow_state: WorkflowRunState,
    *,
    case_root: Path,
    output_dir: Path,
    expected_artifacts: tuple = (),
    default_max_attempts: int = 1,
    max_total_attempts: int | None = None,
    classification_overrides: dict[str, str] | None = None,
    runner: Callable[..., Any] = run_workflow_step,
    sleep: Callable[[float], None] = time.sleep,
    state_path: Path | None = None,
    env: dict[str, str] | None = None,
    driver_context: DriverContext | None = None,
    leases_held: bool = False,
) -> WorkflowRunOutcome:
    """Run one workflow while exclusively owning its case and output."""
    if leases_held:
        if not (
            case_lease_is_held(case_root) and attempt_lease_is_held(output_dir)
        ):
            raise AttemptLeaseError(
                "leases_held=True without owned case and output leases"
            )
        return _run_workflow_locked(
            workflow_dag, workflow_state, case_root=case_root, output_dir=output_dir,
            expected_artifacts=expected_artifacts, default_max_attempts=default_max_attempts,
            max_total_attempts=max_total_attempts,
            classification_overrides=classification_overrides, runner=runner,
            sleep=sleep, state_path=state_path, env=env, driver_context=driver_context,
        )
    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            return _run_workflow_locked(
                workflow_dag, workflow_state, case_root=case_root, output_dir=output_dir,
                expected_artifacts=expected_artifacts, default_max_attempts=default_max_attempts,
                max_total_attempts=max_total_attempts,
                classification_overrides=classification_overrides, runner=runner,
                sleep=sleep, state_path=state_path, env=env, driver_context=driver_context,
            )


def _run_workflow_locked(
    workflow_dag: dict[str, Any],
    workflow_state: WorkflowRunState,
    *,
    case_root: Path,
    output_dir: Path,
    expected_artifacts: tuple = (),
    default_max_attempts: int = 1,
    max_total_attempts: int | None = None,
    classification_overrides: dict[str, str] | None = None,
    runner: Callable[..., Any] = run_workflow_step,
    sleep: Callable[[float], None] = time.sleep,
    state_path: Path | None = None,
    env: dict[str, str] | None = None,
    driver_context: DriverContext | None = None,
) -> WorkflowRunOutcome:
    """Run pending steps to completion, retrying retryable failures.

    The retry decision block (classify -> policy -> backoff -> re-run) is the
    extension point for a future remediation callback, which would drop in
    immediately before the re-run. This path performs no remediation.

    ``max_total_attempts`` caps the number of step executions across the whole
    invocation, including successes and retries; resumed calls get a fresh budget.
    Zero executes no steps. ``None`` disables the ceiling, leaving only the
    per-step ``max_attempts`` bound in force.
    """
    if max_total_attempts is not None and max_total_attempts < 0:
        raise ValueError("max_total_attempts must be non-negative")
    resolved_state_path = state_path or (output_dir / STATE_FILENAME)
    log_dir = output_dir / WORKFLOW_LOGS_DIRNAME
    summaries: dict[str, dict[str, Any]] = {}
    total_attempts = 0

    while workflow_state.current_step_id is not None and workflow_state.status == "pending":
        if max_total_attempts is not None and total_attempts >= max_total_attempts:
            # A zero budget must never dispatch, and a successful step must not
            # bypass the ceiling when another step becomes ready.
            _atomic_write_json(resolved_state_path, workflow_state.to_json())
            break
        step_id = workflow_state.current_step_id
        total_attempts += 1
        context_kwargs = {} if driver_context is None else {"driver_context": driver_context}
        if runner is run_workflow_step:
            context_kwargs["leases_held"] = True
        result = runner(
            workflow_dag,
            workflow_state,
            step_id,
            case_root=case_root,
            log_dir=log_dir,
            state_path=resolved_state_path,
            expected_artifacts=expected_artifacts,
            env=env,
            **context_kwargs,
        )
        workflow_state = result.state
        step_state = _step_state_by_id(workflow_state, step_id)
        summaries[step_id] = {
            "step": step_id,
            "status": "ok" if step_state.status == "completed" else "failed",
            "exit_code": result.exit_code,
            "stdout_log": result.stdout_log,
            "stderr_log": result.stderr_log,
            "attempts": step_state.attempt,
        }
        if step_state.status != "failed":
            continue

        classification = classify_failure(step_state, overrides=classification_overrides)
        max_attempts, backoff_seconds, safe_to_retry = _resolve_policy(
            _step_by_id(workflow_dag, step_id), default_max_attempts
        )
        budget_available = max_total_attempts is None or total_attempts < max_total_attempts
        if (
            classification == "retryable"
            and safe_to_retry
            and step_state.attempt < max_attempts
            and budget_available
        ):
            # Persist a resumable state so a crash during backoff resumes into a
            # retry rather than a refused "failed" state.
            resumable = replace_step_state(
                workflow_state,
                step_state,
                status="pending",
                current_step_id=step_id,
                completed_steps=workflow_state.completed_steps,
                failed_step_id=None,
            )
            _atomic_write_json(resolved_state_path, resumable.to_json())
            workflow_state = resumable
            sleep(backoff_delay(step_state.attempt, backoff_seconds))
            continue
        break  # terminal failure: persisted state remains "failed"

    return WorkflowRunOutcome(state=workflow_state, steps=tuple(summaries.values()))
