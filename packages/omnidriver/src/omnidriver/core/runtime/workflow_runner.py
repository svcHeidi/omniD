from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ..plugin_profile import replica_directory_globs
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
)
from .models import DataArtifact


@dataclass(frozen=True)
class WorkflowStepRunResult:
    state: WorkflowRunState
    step_id: str
    exit_code: int | None
    stdout_log: str
    stderr_log: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_step_id(step_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", step_id).strip("_") or "step"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


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


def _resolve_command(command: str, cwd: Path, driver_context: Any | None = None) -> str:
    """Resolve a step command to what subprocess should execute.

    - Explicit paths (containing ``/`` or an absolute path) are used verbatim
      — the author opted in.
    - A recognized adapter-declared case-script name resolves to the case-local
      executable when present, else falls through to PATH.
    - Any other bare name resolves via PATH only (subprocess does not search
      cwd), so a case directory cannot shadow a trusted binary.
    """
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
    """Build the argv subprocess should exec for one workflow step.

    Case-local adapter scripts are shebang-interpreted by `/bin/sh`,
    which is SIP-protected on macOS: the OS silently strips inherited
    `DYLD_*` environment variables before the script's own body runs, even
    though `env=` correctly carries them into the subprocess call. Values a
    running process sets on itself (as opposed to inheriting via exec)
    survive SIP stripping, so DYLD_* values are re-exported as literal text
    baked into an explicit shell preamble rather than relied upon via `env=`
    alone. Critically, the preamble must `.` (dot-source) the script rather
    than `exec` it: `exec` replaces the process image via another kernel-level
    shebang exec of `/bin/sh`, which re-triggers SIP stripping on the *new*
    process and wipes the just-exported values again; `.` runs the script's
    commands inside the already-running (and now-exported) shell process, so
    no further exec boundary is crossed before the solver process itself forks.
    This is a no-op wrapper (falls through to plain argv) whenever the
    command isn't a case script or there are no DYLD_* values to preserve.

    Dot-sourcing on its own breaks common self-locating case-script idioms
    `cd "${0%/*}"` (self-locate via one's own path): dot-sourcing does not
    update `$0`, which would otherwise remain `/bin/sh`'s own `$0` --
    `${0%/*}` on that resolves to `/bin`, so the script silently `cd`s away
    from the case directory before its real body.
    runs, no-op'ing case-script cleanup with no error. `sh -c cmd name arg...`
    binds `name` to `$0` for the duration of `cmd`, so passing the resolved
    script path as that extra argv element (and the rest of `args` after it,
    read back via "$@") restores `$0` to the script's real path before it is
    dot-sourced, fixing the self-location idiom without reintroducing the
    exec-boundary SIP-stripping problem the dot-source was chosen to avoid.
    """
    if command not in case_script_commands(driver_context) or not env:
        return (executable, *args)
    exports = [f"export {name}={shlex.quote(env[name])}" for name in _DYLD_VAR_NAMES if env.get(name)]
    if not exports:
        return (executable, *args)
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
    """Record matched outputs and directory contents for step attribution.

    Stat changes establish filesystem activity only, not scientific validity.
    Instance-indexed contracts accept both serial and decomposed locations.
    """
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


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    """Terminate a step and descendants that share its owned process group.

    Every step starts a fresh session below, making its PID a group leader.
    This deliberately owns ordinary descendants of a workflow command; a
    descendant that deliberately creates a new session is outside this local
    process contract and must be managed by the invoked program itself.
    """
    if os.name != "posix":
        process.kill()
        process.wait()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return

    # Waiting only for the direct parent is insufficient: it may accept TERM
    # and exit while a child in the same owned group ignores the signal. Keep
    # observing the group itself for the whole grace period, then escalate the
    # still-owned group even if the direct parent has already been reaped.
    deadline = time.monotonic() + 1
    while _has_live_group_members(process) and time.monotonic() < deadline:
        try:
            process.wait(timeout=0)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.02)
    if _has_live_group_members(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.wait()


def _has_live_group_members(process: subprocess.Popen[Any]) -> bool:
    """Whether descendants remain after their direct workflow parent exits."""
    if os.name != "posix":
        return False
    try:
        os.killpg(process.pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def redact_step_logs(paths: Any, patterns: Any) -> None:
    """Replace every match of each pattern, whole, with ``[REDACTED]`` (K9).

    Corrected 2026-09-25 (wave-2 review I3): this used to keep capture group
    1 and replace the rest, so the conventional capture-the-secret pattern
    ``password=(\\S+)`` kept the secret and dropped its label. Groups now mean
    nothing here; a pattern that must keep context around the secret says so
    with lookarounds, e.g. ``(?<=://)[^/\\s@]+(?=@)`` matches only a URL's
    credential."""
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
    process: subprocess.Popen[Any],
    *,
    timeout_s: int | None,
    cancellation_requested: Callable[[], bool] | None,
) -> tuple[int | None, str | None]:
    """Wait for one owned process group, returning an explicit stop reason."""
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    while True:
        if cancellation_requested is not None and cancellation_requested():
            _terminate_process_group(process)
            return None, "cancelled"
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            _terminate_process_group(process)
            return None, "timeout"
        # Poll only when a cancellation hook is supplied; otherwise preserve
        # subprocess' normal blocking wait without a needless wake-up loop.
        wait_timeout = (
            0.1 if remaining is None else min(0.1, remaining)
        ) if cancellation_requested is not None else remaining
        try:
            return process.wait(timeout=wait_timeout), None
        except subprocess.TimeoutExpired:
            if cancellation_requested is None:
                _terminate_process_group(process)
                return None, "timeout"


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
    cancellation_requested: Callable[[], bool] | None = None,
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
                cancellation_requested=cancellation_requested, leases_held=True,
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
    step = _step_by_id(workflow_dag, step_id)
    previous_step_state = _step_state_by_id(workflow_state, step_id)
    if previous_step_state.status not in {"pending", "failed"}:
        raise ValueError(
            f"Workflow step {step_id!r} is {previous_step_state.status!r}; "
            "only pending or failed steps can be run by this low-level runner"
        )
    if not _dependencies_completed(step, workflow_state):
        raise ValueError(f"Workflow step {step_id!r} has incomplete dependencies")

    attempt = previous_step_state.attempt + 1
    # log_dir is required rather than defaulted. The default it replaced --
    # ``case_root / "postProcessing" / "workflow_logs"`` -- was wrong twice
    # over: it hardcoded the default value of ``output_dir_name`` instead of
    # reading it, and it anchored on case_root where every real caller anchors
    # on output_dir. No shipped caller or test ever took it, so it was a dead
    # default silently disagreeing with the live one.
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
    running_step = WorkflowStepState(
        step_id=step_id,
        status="running",
        attempt=attempt,
        command=command,
        args=args,
        cwd=cwd,
        started_at=_utc_now(),
        finished_at=None,
        exit_code=None,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        produced_artifacts=(),
        diagnostics=(),
    )
    running_state = replace_step_state(
        workflow_state,
        running_step,
        status="running",
        current_step_id=step_id,
        completed_steps=workflow_state.completed_steps,
        failed_step_id=None,
    )
    if state_path is not None:
        _atomic_write_json(Path(state_path), running_state.to_json())

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
    try:
        with stdout_log.open("w") as stdout_handle, stderr_log.open("w") as stderr_handle:
            process = subprocess.Popen(
                _argv_for_execution(command, executable, args, env, driver_context),
                cwd=resolved_cwd,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=dict(env) if env is not None else None,
                text=True,
                start_new_session=(os.name == "posix"),
            )
            exit_code, stop_reason = _wait_for_step_process(
                process,
                timeout_s=step.get("timeout_s"),
                cancellation_requested=cancellation_requested,
            )
        if driver_context is not None:
            redact_step_logs((stdout_log, stderr_log), driver_context.capabilities.runtime_evidence.log_redaction_patterns())
        if stop_reason == "timeout":
            diagnostics = ({
                "level": "error",
                "code": "workflow_step_timeout",
                "message": f"Workflow step {step_id!r} timed out after {step.get('timeout_s')} seconds.",
                "field": step_id,
            },)
        elif stop_reason == "cancelled":
            diagnostics = ({
                "level": "error",
                "code": "workflow_step_cancelled",
                "message": f"Workflow step {step_id!r} was cancelled by its caller.",
                "field": step_id,
            },)
        elif _has_live_group_members(process):
            # A zero-exit launcher that backgrounds work is not a completed
            # workflow step.  Stop the residual owned group rather than
            # allowing it to race a retry or a later attempt.
            _terminate_process_group(process)
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
        finished_at=_utc_now(),
        exit_code=exit_code,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        produced_artifacts=produced_artifacts,
        diagnostics=diagnostics,
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
        _atomic_write_json(Path(state_path), final_state.to_json())

    return WorkflowStepRunResult(
        state=final_state,
        step_id=step_id,
        exit_code=exit_code,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )
