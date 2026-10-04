from __future__ import annotations

import os
import re
import shlex
import socket
import subprocess
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..plugin_profile import replica_directory_globs
from ..scripts import find_script, script_argv
from .transaction_mechanics import atomic_write_json
from .workflow import case_script_commands
from .attempt_lease import (
    AttemptLeaseError,
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from .workflow_state import (
    WorkflowRunState,
    WorkflowStepState,
    replace_step_state,
    workflow_state_from_json,
)
from .models import DataArtifact
from .process_control import (
    group_alive,
    recorded_here,
    register,
    spawning,
    stop_requested,
    terminate_group,
    terminate_process,
    unregister,
)


@dataclass(frozen=True)
class WorkflowStepRunResult:
    state: WorkflowRunState
    step_id: str
    exit_code: int | None
    stdout_log: str
    stderr_log: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_step_id(step_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", step_id).strip("_") or "step"


def _host_facts(command, args, env, driver_context) -> dict[str, Any]:
    """Ambient host facts plus the values of the stack's declared environment variables."""
    from .host_facts import host_facts

    declared: tuple[str, ...] = ()
    if driver_context is not None:
        from omnidriver.core.environment_connection import stack_connection

        connection, _ = stack_connection(driver_context)
        declared = tuple(variable.name for variable in connection.supplied)
    return host_facts(command, args, env, declared_variables=declared)


def _step_by_id(workflow_dag: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in workflow_dag.get("steps", ()):
        if isinstance(step, dict) and step.get("id") == step_id:
            return step
    raise KeyError(f"Workflow step {step_id!r} does not exist")


def _step_state_by_id(state: WorkflowRunState, step_id: str) -> WorkflowStepState:
    for step_state in state.steps:
        if step_state.step_id == step_id:
            return step_state
    raise KeyError(f"Workflow state has no step {step_id!r}")


def _next_runnable_step_id(
    workflow_dag: dict[str, Any],
    state: WorkflowRunState,
) -> str | None:
    completed = set(state.completed_steps)
    states_by_id = {step.step_id: step for step in state.steps}
    for step in workflow_dag.get("steps", ()):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id", ""))
        step_state = states_by_id.get(step_id)
        if step_state is None or step_state.status != "pending":
            continue
        depends_on = step.get("depends_on", [])
        if isinstance(depends_on, list) and all(str(dep) in completed for dep in depends_on):
            return step_id
    return None


def _dependencies_completed(
    step: dict[str, Any],
    state: WorkflowRunState,
) -> bool:
    completed = set(state.completed_steps)
    depends_on = step.get("depends_on", [])
    return isinstance(depends_on, list) and all(str(dep) in completed for dep in depends_on)


def check_step_runnable(
    workflow_dag: dict[str, Any], workflow_state: WorkflowRunState, step_id: str,
) -> None:
    """Refuse, by name, a step that is neither pending nor failed, or whose dependencies are not completed."""
    step = _step_by_id(workflow_dag, step_id)
    status = _step_state_by_id(workflow_state, step_id).status
    if status not in {"pending", "failed"}:
        raise ValueError(
            f"Workflow step {step_id!r} is {status!r}; "
            "only a pending or failed step can run; plan again to start over"
        )
    if not _dependencies_completed(step, workflow_state):
        raise ValueError(f"Workflow step {step_id!r} has incomplete dependencies")


def _resolve_command(command: str, cwd: Path, driver_context: Any | None = None) -> str:
    """Paths verbatim; a declared case-script name case-locally when present; any other bare name via PATH only."""
    if "/" in command:
        return command
    if command in case_script_commands(driver_context):
        local_command = cwd / command
        if local_command.is_file() and os.access(local_command, os.X_OK):
            return str(local_command)
    return command


_DYLD_VAR_NAMES = (
    "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH",
    "DYLD_INSERT_LIBRARIES",
)


def _argv_for_execution(
    command: str,
    executable: str,
    args: tuple[str, ...],
    env: Mapping[str, str] | None,
    driver_context: Any | None = None,
) -> tuple[str, ...]:
    """The argv subprocess should exec for one step."""
    step_env = os.environ if env is None else env
    script = find_script(command, driver_context)
    if script is not None:
        return (*script_argv(script, step_env), *args)
    if command not in case_script_commands(driver_context) or not env:
        return (executable, *args)
    exports = [f"export {name}={shlex.quote(env[name])}" for name in _DYLD_VAR_NAMES if env.get(name)]
    if not exports:
        return (executable, *args)
    # macOS SIP makes /bin/sh strip DYLD_* from a shebang-run script, so re-export them and dot-source it;
    # passing the script as `sh -c`'s name rebinds $0, which keeps the `cd "${0%/*}"` idiom working.
    preamble = "; ".join(exports) + '; . "$0" "$@"'
    return ("/bin/sh", "-c", preamble, executable, *args)


def _resolve_case_cwd(case_root: Path, cwd: str) -> Path:
    root = Path(case_root).resolve()
    resolved = (root / cwd).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Workflow cwd {cwd!r} escapes case root {root}") from exc
    return resolved


def _artifact_snapshot(
    case_root: Path, artifact: DataArtifact, driver_context: Any | None,
) -> dict[Path, tuple[int, int, int, int]]:
    """Stat the outputs matching ``artifact`` (serial and decomposed locations) for step attribution."""
    import glob

    expanded = artifact.path_pattern.format(case_id=case_root.name, instance="*")
    patterns = [str(case_root / expanded)]
    if artifact.instance_indexed:
        for replica_glob in replica_directory_globs(driver_context):
            patterns.append(str(case_root / replica_glob / expanded))
    snapshot = {}
    for pattern in patterns:
        for match in glob.glob(pattern):
            path = Path(match)
            paths = [path]
            if path.is_dir():
                paths.extend(path.rglob("*"))
            for entry in paths:
                try:
                    stat = entry.stat()
                except FileNotFoundError:
                    continue
                snapshot[entry] = (
                    stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino,
                )
    return snapshot


def settle_interrupted_steps(state: WorkflowRunState, state_path: Path) -> WorkflowRunState:
    """Fail a step a dead process left ``running`` as interrupted, and save that; refuse while it is alive.

    The step stays rerunnable like any failed step, and its attempt counter
    is kept, so the rerun writes new logs beside the interrupted attempt's.
    """
    running = [step for step in state.steps if step.status == "running"]
    for step in running:
        if step.pid is not None and (step.host or {}).get("hostname") not in (None, socket.gethostname()):
            raise ValueError(
                f"step {step.step_id!r} was started on host {step.host['hostname']!r}, so it cannot be "
                "known to have stopped; resume it there, or plan again"
            )
        if recorded_here(step) and group_alive(step.pid):
            raise ValueError(
                f"step {step.step_id!r} is still running (process group {step.pid}); stop it before resuming"
            )
    for step in running:
        interrupted = replace(
            step, status="failed", finished_at=utc_now(), pid=None,
            diagnostics=(*step.diagnostics, {
                "level": "error",
                "code": "workflow_step_interrupted",
                "message": (
                    f"Workflow step {step.step_id!r} was left running by a process that is gone; "
                    "the attempt's logs are kept and a rerun is a new attempt."
                ),
                "field": step.step_id,
            }),
        )
        state = replace_step_state(
            state, interrupted, status="failed", current_step_id=step.step_id,
            completed_steps=state.completed_steps, failed_step_id=step.step_id,
        )
    if running:
        atomic_write_json(Path(state_path), state.to_json())
    return state


#: How much of the end of each log a stack reads to explain a failed step.
_EXPLAINED_LOG_BYTES = 65536


def _explained_by_the_logs(
    step_id: str, logs: tuple[Path, ...], case_root: Path, driver_context: Any,
) -> tuple[dict[str, Any], ...]:
    """Step diagnostics the stack reads from the end of ``logs`` to explain a failure."""
    text = ""
    for log in logs:
        try:
            with log.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - _EXPLAINED_LOG_BYTES))
                text += handle.read().decode("utf-8", errors="replace") + "\n"
        except OSError:
            continue
    found = driver_context.stack.call("explain_step_failure", text, case_root, driver_context=driver_context)
    return tuple({**asdict(item), "field": item.field or step_id} for item in found)


def redact_step_logs(paths: Any, patterns: Any) -> None:
    """Replace every match of each pattern, whole, with ``[REDACTED]``.

    Capture groups are not preserved: a pattern that must keep context
    around the secret uses lookarounds instead, e.g.
    ``(?<=://)[^/\\s@]+(?=@)`` matches only a URL's credential."""
    compiled = [re.compile(p) for p in patterns]
    if not compiled:
        return
    for path in paths:
        if not Path(path).is_file():
            continue
        text = Path(path).read_text(errors="replace")
        redacted = text
        for pattern in compiled:
            redacted = pattern.sub(lambda _match: "[REDACTED]", redacted)
        if redacted != text:
            Path(path).write_text(redacted)


def _wait_for_step_process(
    process: subprocess.Popen[Any], *, timeout_s: int | None,
) -> tuple[int | None, str | None]:
    """Wait for a step, ending its group on a timeout or a stop request; returns the exit code and the stop reason."""
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    while True:
        if stop_requested():
            terminate_process(process)
            return None, "stopped"
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            terminate_process(process)
            return None, "timeout"
        try:
            return process.wait(timeout=0.1 if remaining is None else min(0.1, remaining)), None
        except subprocess.TimeoutExpired:
            continue


def run_workflow_step(
    workflow_dag: dict[str, Any],
    workflow_state: WorkflowRunState,
    step_id: str,
    *,
    case_root: Path,
    log_dir: Path,
    state_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    expected_artifacts: tuple[DataArtifact, ...] = (),
    driver_context: Any | None = None,
    leases_held: bool = False,
) -> WorkflowStepRunResult:
    """Execute one normalized workflow step and return the updated state.

    This intentionally does not implement resume, retry loops, or multi-step
    orchestration. It only performs one subprocess transition and records logs.
    """
    lease_dir = Path(state_path).parent if state_path is not None else Path(log_dir).parent
    owns_both = (
        case_lease_is_held(case_root) and attempt_lease_is_held(lease_dir)
    )
    if leases_held and not owns_both:
        raise AttemptLeaseError("leases_held=True without owned case and output leases")
    if not leases_held and not owns_both:
        with ExitStack() as stack:
            if not case_lease_is_held(case_root):
                stack.enter_context(acquire_case_lease(case_root))
            if not attempt_lease_is_held(lease_dir):
                stack.enter_context(acquire_attempt_lease(lease_dir))
            return run_workflow_step(
                workflow_dag, workflow_state, step_id,
                case_root=case_root, log_dir=log_dir, state_path=state_path, env=env,
                expected_artifacts=expected_artifacts, driver_context=driver_context,
                leases_held=True,
            )

    from .workflow_state import workflow_digest

    digest = workflow_digest(workflow_dag)
    if workflow_state.workflow_digest is not None and workflow_state.workflow_digest != digest:
        raise ValueError("Workflow state belongs to a different DAG")
    workflow_state = replace(workflow_state, workflow_digest=digest)
    if driver_context is not None:
        from .resume import checkpoint_snapshot

        workflow_state = replace(workflow_state, resume_snapshot=checkpoint_snapshot(
            case_root, workflow_dag, driver_context, env
        ))
    check_step_runnable(workflow_dag, workflow_state, step_id)
    step = _step_by_id(workflow_dag, step_id)
    previous_step_state = _step_state_by_id(workflow_state, step_id)

    attempt = previous_step_state.attempt + 1
    # log_dir is required rather than defaulted: a default anchored on
    # case_root would disagree with the output_dir every real caller uses.
    resolved_log_dir = Path(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    safe_id = _safe_step_id(step_id)
    stdout_log = resolved_log_dir / f"{safe_id}.attempt{attempt}.stdout.log"
    stderr_log = resolved_log_dir / f"{safe_id}.attempt{attempt}.stderr.log"

    args = tuple(str(arg) for arg in step.get("args", ()))
    cwd = str(step.get("cwd", "."))
    command = str(step["command"])
    resolved_cwd = _resolve_case_cwd(Path(case_root), cwd)
    executable = _resolve_command(command, resolved_cwd, driver_context)
    host = _host_facts(command, args, env, driver_context)
    running_step = WorkflowStepState(
        step_id=step_id,
        status="running",
        attempt=attempt,
        command=command,
        args=args,
        cwd=cwd,
        started_at=utc_now(),
        finished_at=None,
        exit_code=None,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        produced_artifacts=(),
        diagnostics=(),
        host=host,
    )
    running_state = replace_step_state(
        workflow_state,
        running_step,
        status="running",
        current_step_id=step_id,
        completed_steps=workflow_state.completed_steps,
        failed_step_id=None,
    )
    required_artifacts = tuple(
        artifact for artifact in expected_artifacts
        if not artifact.optional and artifact.artifact_id in step.get("produces", ())
    )
    artifacts_before = tuple(
        _artifact_snapshot(Path(case_root), artifact, driver_context)
        for artifact in required_artifacts
    )

    exit_code: int | None = None
    diagnostics: tuple[dict[str, Any], ...] = ()
    started = time.time()
    try:
        with stdout_log.open("w") as stdout_handle, stderr_log.open("w") as stderr_handle:
            with spawning():
                process = subprocess.Popen(
                    _argv_for_execution(command, executable, args, env, driver_context),
                    cwd=resolved_cwd,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    # A shell-started tool compares $PWD with getcwd() and warns when they differ.
                    env={**(os.environ if env is None else env), "PWD": os.path.realpath(resolved_cwd)},
                    text=True,
                    start_new_session=(os.name == "posix"),
                )
                register(process)
            try:
                # The running state is first written here, with the pid, so
                # a state that says running always says which process.
                if state_path is not None:
                    atomic_write_json(Path(state_path), replace_step_state(
                        running_state, replace(running_step, pid=process.pid), status="running",
                        current_step_id=step_id, completed_steps=workflow_state.completed_steps,
                        failed_step_id=None,
                    ).to_json())
                exit_code, stop_reason = _wait_for_step_process(process, timeout_s=step.get("timeout_s"))
            finally:
                unregister(process)
        if driver_context is not None:
            redact_step_logs((stdout_log, stderr_log), driver_context.stack.call("get_log_redaction_patterns"))
        if stop_reason == "timeout":
            diagnostics = ({
                "level": "error",
                "code": "workflow_step_timeout",
                "message": f"Workflow step {step_id!r} timed out after {step.get('timeout_s')} seconds.",
                "field": step_id,
            },)
        elif stop_reason == "stopped":
            diagnostics = ({
                "level": "error",
                "code": "workflow_step_cancelled",
                "message": f"Workflow step {step_id!r} was stopped by a signal.",
                "field": step_id,
            },)
        elif group_alive(process.pid):
            # A zero-exit launcher that backgrounds work is not a completed
            # workflow step.  Stop the residual owned group rather than
            # allowing it to race a retry or a later attempt.
            terminate_group(process.pid)
            diagnostics = ({
                "level": "error",
                "code": "workflow_step_orphaned_descendants",
                "message": f"Workflow step {step_id!r} exited while owned descendants were still running.",
                "field": step_id,
            },)
    except subprocess.TimeoutExpired as exc:
        # Kept for defensive compatibility with alternate Popen-like test
        # doubles; the owned wait helper normally handles timeouts itself.
        diagnostics = ({
            "level": "error",
            "code": "workflow_step_timeout",
            "message": f"Workflow step {step_id!r} timed out after {exc.timeout} seconds.",
            "field": step_id,
        },)
    except OSError as exc:
        diagnostics = ({
            "level": "error",
            "code": "workflow_step_exec_error",
            "message": str(exc),
            "field": step_id,
        },)

    if exit_code is not None and not diagnostics and driver_context is not None:
        solver_logs = tuple(
            log for log in driver_context.stack.call("get_step_log_files", resolved_cwd)
            if log.is_file() and log.stat().st_mtime >= started
        )
        captured = (stdout_log, stderr_log) if exit_code != 0 else ()
        if captured or solver_logs:
            diagnostics = _explained_by_the_logs(
                step_id, (*captured, *solver_logs), Path(case_root), driver_context,
            )

    status = "completed" if exit_code == 0 and not diagnostics else "failed"
    produced_artifacts = tuple(str(item) for item in step.get("produces", ())) if status == "completed" else ()

    if status == "completed" and required_artifacts:
        missing_artifacts = []
        stale_artifacts = []
        for artifact, before in zip(required_artifacts, artifacts_before):
            after = _artifact_snapshot(Path(case_root), artifact, driver_context)
            if not after:
                missing_artifacts.append(artifact.artifact_id)
            elif not any(before.get(path) != signature for path, signature in after.items()):
                stale_artifacts.append(artifact.artifact_id)
        for code, artifact_ids, detail in (
            ("missing_artifacts", missing_artifacts, "missing expected artifacts"),
            ("stale_artifacts", stale_artifacts, "unchanged expected artifacts"),
        ):
            if artifact_ids:
                status = "failed"
                produced_artifacts = ()
                diagnostics = (*diagnostics, {
                    "level": "error",
                    "code": code,
                    "message": f"Step {step_id!r} exited successfully but has {detail}: {', '.join(artifact_ids)}",
                    "field": step_id,
                })

    final_step = WorkflowStepState(
        step_id=step_id,
        status=status,
        attempt=attempt,
        command=command,
        args=args,
        cwd=cwd,
        started_at=running_step.started_at,
        finished_at=utc_now(),
        exit_code=exit_code,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        produced_artifacts=produced_artifacts,
        diagnostics=diagnostics,
        host=host,
    )

    completed_steps = workflow_state.completed_steps
    if status == "completed" and step_id not in completed_steps:
        completed_steps = (*completed_steps, step_id)

    provisional_state = replace_step_state(
        running_state,
        final_step,
        status="failed" if status == "failed" else "pending",
        current_step_id=step_id if status == "failed" else None,
        completed_steps=completed_steps,
        failed_step_id=step_id if status == "failed" else None,
    )
    if status == "completed":
        next_step_id = _next_runnable_step_id(workflow_dag, provisional_state)
        run_status = "pending" if next_step_id is not None else "completed"
        final_state = replace_step_state(
            provisional_state,
            final_step,
            status=run_status,
            current_step_id=next_step_id,
            completed_steps=completed_steps,
            failed_step_id=None,
        )
    else:
        final_state = provisional_state

    if driver_context is not None:
        final_state = replace(final_state, resume_snapshot=checkpoint_snapshot(
            case_root, workflow_dag, driver_context, env
        ))
    if state_path is not None:
        atomic_write_json(Path(state_path), final_state.to_json())

    return WorkflowStepRunResult(
        state=final_state,
        step_id=step_id,
        exit_code=exit_code,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )
