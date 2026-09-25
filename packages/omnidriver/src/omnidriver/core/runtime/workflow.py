from __future__ import annotations

import os
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePath
from typing import Any, Iterable

from .artifacts import DRIVER_PRODUCED_BY_VALUES
from .models import DataArtifact
from omnidriver.core.plugin_profile import entrypoint_relpaths


STEP_STATUS_VALUES = ("pending", "running", "completed", "failed", "skipped")


# Single owner of the command allowlist, shared by strict_planning and the
# run-document adapter (see threat model in the RunDocument execution plan).
# Core-only process commands, always allowed and resolved via PATH. Solver and
# environment commands arrive through CommandAuthorizationCapability; Core
# must not name either kind here.
CORE_NEUTRAL_COMMANDS = frozenset(
    {
        "mpirun",
        "mpiexec",
        "orterun",
    }
)

# Compatibility name for older callers. Core itself declares no case-local
# command names; adapters provide them through runtime conventions.
CASE_SCRIPT_COMMANDS = frozenset()

def case_script_commands(driver_context: Any | None) -> frozenset[str]:
    """Bare command names that may resolve to a case-LOCAL executable, for
    the active plugin.

    The active adapter supplies case-local command names through its runtime
    convention declaration. Core adds only the adapter's declared entrypoint
    paths; with no context the set is empty.

    The value flowing in here is set in the plugin's own static profile,
    never touched by an agent-authored ``RunDocument`` or case-folder
    content -- the two things this module's trust boundary actually
    distrusts (see the threat model doc above) -- so widening this set to
    a plugin's own declared name does not change who can shadow PATH.
    """
    if driver_context is None:
        return frozenset()
    conventions = driver_context.capabilities.case_runtime_conventions.conventions()
    return frozenset(conventions.case_script_commands) | frozenset(
        entrypoint_relpaths(driver_context)
    )


# MPI launcher recognition: generic to any parallel workflow step (OpenMPI,
# MPICH, ...), not OpenFOAM-specific. Moved here from
# omnidriver.openfoam.environment_preflight, which had no OpenFOAM content in
# either constant -- environment_preflight now imports these back from core.
_MPI_LAUNCHERS = frozenset({"mpirun", "mpiexec", "orterun"})
_MPI_VALUE_FLAGS = frozenset({"-np", "-n", "--np"})


def _unwrap_mpi_program(args: tuple[str, ...]) -> str | None:
    """Return the wrapped program from an MPI launcher's args, or None."""
    index = 0
    while index < len(args):
        token = args[index]
        if token in _MPI_VALUE_FLAGS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


@dataclass(frozen=True)
class WorkflowDiagnostic:
    level: str
    code: str
    message: str
    field: str = ""


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    command: str
    args: tuple[str, ...] = ()
    cwd: str = "."
    depends_on: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    timeout_s: int | None = None
    retry_policy: dict[str, Any] = field(default_factory=dict)
    command_display: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["args"] = list(self.args)
        payload["depends_on"] = list(self.depends_on)
        payload["produces"] = list(self.produces)
        payload["consumes"] = list(self.consumes)
        if payload["timeout_s"] is None:
            payload.pop("timeout_s")
        return payload


def _string_list(value: Any, *, field_name: str) -> tuple[tuple[str, ...], WorkflowDiagnostic | None]:
    if value is None:
        return (), None
    if not isinstance(value, list):
        return (), WorkflowDiagnostic(
            level="error",
            code="invalid_workflow_field",
            message=f"Workflow field {field_name!r} must be a list of strings.",
            field=field_name,
        )
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return (), WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_field",
                message=f"Workflow field {field_name!r} must be a list of strings.",
                field=field_name,
            )
        strings.append(item)
    return tuple(strings), None


def _command_parts(raw_command: Any) -> tuple[str, tuple[str, ...], str, WorkflowDiagnostic | None]:
    if isinstance(raw_command, str):
        try:
            parts = shlex.split(raw_command)
        except ValueError as exc:
            return "", (), raw_command, WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_command",
                message=str(exc),
                field="command",
            )
        if not parts:
            return "", (), raw_command, WorkflowDiagnostic(
                level="error",
                code="workflow_step_without_command",
                message="Workflow step has an empty command.",
                field="command",
            )
        return parts[0], tuple(parts[1:]), raw_command, None
    if isinstance(raw_command, list) and raw_command and all(isinstance(item, str) for item in raw_command):
        return raw_command[0], tuple(raw_command[1:]), shlex.join(raw_command), None
    return "", (), "", WorkflowDiagnostic(
        level="error",
        code="invalid_workflow_command",
        message="Workflow command must be a string or non-empty argv list.",
        field="command",
    )


def _cwd_is_case_relative(cwd: str) -> bool:
    path = PurePath(cwd)
    return not path.is_absolute() and ".." not in path.parts


def normalize_workflow_dag(
    raw_dag: dict[str, Any] | None,
    *,
    expected_artifacts: Iterable[DataArtifact] = (),
    utility_produces: dict[str, tuple[str, ...]] | None = None,
    driver_context: Any,
) -> tuple[dict[str, Any] | None, tuple[WorkflowDiagnostic, ...]]:
    """Return an executable-shaped workflow DAG without executing it.

    Existing specs still author the compact form, for example
    ``{"command": "postProcess -func points"}``. Strict planning uses this
    normalizer to expose a stable argv-like contract for a future step runner.

    ``driver_context`` is required, not defaulted: it selects which steps may
    be credited with unclaimed expected artifacts. A forgotten kwarg would
    silently change the returned document (artifacts attached to a different
    step, or to none) with no diagnostic, so the caller must pass it — ``None``
    is still accepted, and means "no plugin solver is authorized".
    """
    if raw_dag is None:
        return None, (
            WorkflowDiagnostic(
                level="error",
                code="missing_workflow_dag",
                message=(
                    "Strict planning requires a workflow_dag with steps. A case "
                    "folder needs an executable entrypoint declared by its adapter."
                ),
                field="workflow_dag",
            ),
        )
    raw_steps = raw_dag.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None, (
            WorkflowDiagnostic(
                level="error",
                code="missing_workflow_steps",
                message="Strict planning requires workflow_dag.steps to be a non-empty list.",
                field="workflow_dag.steps",
            ),
        )

    diagnostics: list[WorkflowDiagnostic] = []
    steps: list[WorkflowStep] = []
    seen_ids: set[str] = set()
    utility_produces = utility_produces or {}
    claimed_artifacts: set[str] = set()
    artifact_ids = tuple(artifact.artifact_id for artifact in expected_artifacts)

    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_step",
                message="Workflow step must be an object.",
                field=f"workflow_dag.steps[{index}]",
            ))
            continue

        step_id = str(raw_step.get("id", "")).strip()
        if not step_id:
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="workflow_step_without_id",
                message="Workflow step id must be a non-empty string.",
                field=f"workflow_dag.steps[{index}].id",
            ))
            step_id = f"step-{index + 1}"
        if step_id in seen_ids:
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="duplicate_workflow_step_id",
                message=f"Workflow step id {step_id!r} is duplicated.",
                field=f"workflow_dag.steps[{index}].id",
            ))
        seen_ids.add(step_id)

        command, parsed_args, command_display, command_error = _command_parts(raw_step.get("command"))
        if command_error is not None:
            diagnostics.append(command_error)

        explicit_args, args_error = _string_list(raw_step.get("args"), field_name="args")
        if args_error is not None:
            diagnostics.append(args_error)
        depends_on, depends_error = _string_list(raw_step.get("depends_on"), field_name="depends_on")
        if depends_error is not None:
            diagnostics.append(depends_error)
        produces, produces_error = _string_list(raw_step.get("produces"), field_name="produces")
        if produces_error is not None:
            diagnostics.append(produces_error)
        consumes, consumes_error = _string_list(raw_step.get("consumes"), field_name="consumes")
        if consumes_error is not None:
            diagnostics.append(consumes_error)

        # Union, never replace (fix round 1 I6, 2026-09-25): before K4 a
        # step's own ``produces`` replaced its utility manifest's. Once a
        # record step could declare ``produces``, that dropped the manifest
        # ids, left them unclaimed, and the unclaimed branch below credited
        # them to the last solver step, which then failed for a file it
        # never writes. No step in packages/*/src relied on replacement.
        produces = tuple(dict.fromkeys((*produces, *utility_produces.get(command, ()))))
        if produces:
            claimed_artifacts.update(produces)

        retry_policy = raw_step.get("retry_policy", {})
        if not isinstance(retry_policy, dict):
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_field",
                message="Workflow field 'retry_policy' must be an object.",
                field="retry_policy",
            ))
            retry_policy = {}
        else:
            retry_policy = dict(retry_policy)
            max_attempts = retry_policy.get("max_attempts")
            if max_attempts is not None and (
                isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < 1
            ):
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="invalid_workflow_field",
                    message="Workflow field 'retry_policy.max_attempts' must be an integer >= 1.",
                    field="retry_policy.max_attempts",
                ))
                del retry_policy["max_attempts"]
            backoff_seconds = retry_policy.get("backoff_seconds")
            if backoff_seconds is not None and (
                isinstance(backoff_seconds, bool)
                or not isinstance(backoff_seconds, (int, float))
                or backoff_seconds < 0
            ):
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="invalid_workflow_field",
                    message="Workflow field 'retry_policy.backoff_seconds' must be a number >= 0.",
                    field="retry_policy.backoff_seconds",
                ))
                del retry_policy["backoff_seconds"]
            safe_to_retry = retry_policy.get("safe_to_retry")
            if safe_to_retry is not None and not isinstance(safe_to_retry, bool):
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="invalid_workflow_field",
                    message="Workflow field 'retry_policy.safe_to_retry' must be a boolean.",
                    field="retry_policy.safe_to_retry",
                ))
                del retry_policy["safe_to_retry"]
            if retry_policy.get("max_attempts", 1) > 1 and safe_to_retry is not True:
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="unsafe_retry_policy",
                    message=(
                        "Workflow retries require retry_policy.safe_to_retry: true "
                        "on the affected step."
                    ),
                    field="retry_policy.safe_to_retry",
                ))

        timeout_s = raw_step.get("timeout_s")
        if timeout_s is not None and (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, int)
            or timeout_s <= 0
        ):
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_field",
                message="Workflow field 'timeout_s' must be a positive integer.",
                field="timeout_s",
            ))
            timeout_s = None

        cwd = raw_step.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd:
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="invalid_workflow_field",
                message="Workflow field 'cwd' must be a non-empty string.",
                field="cwd",
            ))
            cwd = "."
        elif not _cwd_is_case_relative(cwd):
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="workflow_cwd_not_case_relative",
                message="Workflow field 'cwd' must stay inside the case directory.",
                field="cwd",
            ))

        steps.append(WorkflowStep(
            id=step_id,
            command=command,
            args=parsed_args + explicit_args,
            cwd=cwd,
            depends_on=depends_on,
            produces=produces,
            consumes=consumes,
            timeout_s=timeout_s,
            retry_policy=retry_policy,
            command_display=command_display or command,
        ))

    known_ids = {step.id for step in steps}
    dependencies_by_id = {step.id: step.depends_on for step in steps}
    for step in steps:
        for dependency in step.depends_on:
            if dependency == step.id:
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="workflow_step_self_dependency",
                    message=f"Workflow step {step.id!r} depends on itself.",
                    field=step.id,
                ))
            elif dependency not in known_ids:
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="unknown_workflow_dependency",
                    message=f"Workflow step {step.id!r} depends on unknown step {dependency!r}.",
                    field=step.id,
                ))

    visited: set[str] = set()
    visiting: set[str] = set()
    cycle_reported = False

    def visit(step_id: str) -> None:
        nonlocal cycle_reported
        if step_id in visited:
            return
        if step_id in visiting:
            if not cycle_reported:
                diagnostics.append(WorkflowDiagnostic(
                    level="error",
                    code="workflow_dependency_cycle",
                    message="Workflow dependencies must form an acyclic graph.",
                    field=step_id,
                ))
                cycle_reported = True
            return
        visiting.add(step_id)
        for dependency in dependencies_by_id.get(step_id, ()):
            if dependency in dependencies_by_id:
                visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step in steps:
        visit(step.id)

    unclaimed_artifacts = tuple(artifact_id for artifact_id in artifact_ids if artifact_id not in claimed_artifacts)
    if unclaimed_artifacts:
        # Only run-style steps may be credited with producing artifacts: the
        # case run script plus whatever solver binaries the context authorizes.
        # Cleanup and other adapter-declared scripts are deliberately excluded
        # from artifact credit. Note solver_commands() only,
        # NOT the full authorized set: auxiliary_commands() are authorized to
        # run but are post-processing, and ``produces`` is enforced per-step
        # (workflow_runner's missing_artifacts check), so crediting one would
        # make a silent solver fail the wrong step.
        # The entrypoint comes from the plugin's declared role, not a literal:
        # registry.py already resolved it that way for case detection, so
        # Resolving the entrypoint from adapter declarations keeps a plugin
        # whose entrypoint has another name in the producer set.
        producer_commands = set(entrypoint_relpaths(driver_context))
        if driver_context is not None:
            producer_commands |= (
                driver_context.capabilities.command_authorization.solver_commands()
            )
        artifact_producer_steps = [
            step for step in steps if step.command in producer_commands
        ]
        if artifact_producer_steps:
            target_id = artifact_producer_steps[-1].id
            steps = [
                (
                    WorkflowStep(
                        id=step.id,
                        command=step.command,
                        args=step.args,
                        cwd=step.cwd,
                        depends_on=step.depends_on,
                        produces=tuple(dict.fromkeys((*step.produces, *unclaimed_artifacts))),
                        consumes=step.consumes,
                        timeout_s=step.timeout_s,
                        retry_policy=step.retry_policy,
                        command_display=step.command_display,
                    )
                    if step.id == target_id else step
                )
                for step in steps
            ]

    return {
        "schema_version": "1",
        "step_status_values": list(STEP_STATUS_VALUES),
        "steps": [step.to_json() for step in steps],
    }, tuple(diagnostics)


def workflow_output_artifacts(
    artifacts: Iterable[DataArtifact],
) -> tuple[DataArtifact, ...]:
    """Return artifacts whose existence is a responsibility of a workflow step.

    ``expectedArtifacts`` also records omnidriver's own state and log files.
    Those files are created by the executor around a step transition, rather
    than by the solver command itself, so assigning them to a normalized step
    would make the solver incorrectly responsible for driver bookkeeping.
    """
    return tuple(
        artifact for artifact in artifacts
        if artifact.produced_by not in DRIVER_PRODUCED_BY_VALUES
    )


def _is_authorized(command: str, driver_context: Any) -> bool:
    """Return whether ``command`` is in the accepted command surface.

    This is the ONE definition of "authorized" for a bare command name:
    the union of :data:`CORE_NEUTRAL_COMMANDS`, :func:`case_script_commands`,
    and -- when a ``driver_context`` is given -- the commands its
    ``CommandAuthorizationCapability`` grants (``environment_commands``,
    ``solver_commands() | auxiliary_commands()``, a ``utility_manifests()``
    entry that declares ``produces``, and ``is_installed_environment_command``
    as a runtime fallback). ``validate_workflow_commands`` calls this for
    both a step's own command and, when that command is an MPI launcher, the
    program it wraps -- a second, independent notion of "authorized" for the
    wrapped program is exactly how it escaped review (an ``mpirun`` step was
    accepted from :data:`CORE_NEUTRAL_COMMANDS` alone, and the binary it
    wrapped was never checked against this surface at all).

    Preserves the original per-step precedence: a utility manifest, once
    present, decides the outcome for that command on its own (``produces``
    or not) and is never overridden by ``is_installed_environment_command``.
    """
    if command in CORE_NEUTRAL_COMMANDS or command in case_script_commands(driver_context):
        return True
    if driver_context is None:
        return False
    authorization = driver_context.capabilities.command_authorization
    # Authorization is the union: both kinds of plugin command may run. The
    # split between solver and auxiliary matters only to the
    # artifact-producer heuristic in normalize_workflow_dag, not here.
    if (
        command in authorization.environment_commands()
        or command in authorization.solver_commands() | authorization.auxiliary_commands()
    ):
        return True
    manifest = authorization.utility_manifests().get(command)
    if manifest is not None:
        return bool(manifest.produces)
    return authorization.is_installed_environment_command(command)


def validate_workflow_commands(
    workflow_dag: dict[str, Any] | None,
    *,
    driver_context: Any = None,
) -> tuple[WorkflowDiagnostic, ...]:
    """Reject DAG steps whose command is not on the allowlist.

    The allowlist is the union of :data:`CORE_NEUTRAL_COMMANDS`, the commands
    ``driver_context`` authorizes through its
    ``CommandAuthorizationCapability``, :func:`case_script_commands` (the
    active adapter's declared case scripts and entrypoints), that context's
    utility manifests that declare ``produces``,
    and applications the active environment recognizes at runtime -- see
    :func:`_is_authorized`, the single function that decides this for a bare
    command name. Without a ``driver_context`` no environment, plugin
    command, or utility is authorized, leaving only core-neutral commands and
    case scripts. An explicit path form (``command`` containing ``/``) is
    allowed only as ``./<name>`` where ``<name>`` is an adapter-declared case
    script — this keeps the gate in parity with ``_resolve_command`` while
    still refusing arbitrary ``./script`` and absolute paths. This is the one
    owner of the command allowlist; both ``strict_plan`` and the run-document
    adapter call it so neither can drift. Runs on the *normalized* DAG, where
    ``command`` is the bare executable (args already split out).

    A step whose command is an MPI launcher (:data:`_MPI_LAUNCHERS`) is
    additionally checked on the program its args wrap: an authorized
    launcher does not authorize an arbitrary wrapped binary, since
    :func:`_is_authorized` is applied to that program too.
    """
    case_scripts = case_script_commands(driver_context)
    if driver_context is not None:
        utilities = driver_context.capabilities.command_authorization.utility_manifests()
    else:
        utilities = {}

    diagnostics: list[WorkflowDiagnostic] = []
    for step in (workflow_dag or {}).get("steps", ()):
        command = step.get("command", "")
        step_id = str(step.get("id", ""))
        if not command:
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="workflow_step_without_command",
                message=f"Workflow step {step_id or '<unknown>'!r} has no command.",
                field=step_id,
            ))
            continue
        if "/" in command:
            # Explicit path form. Only ``./<case-script>`` is permitted (gate
            # parity with _resolve_command); an arbitrary ``./script`` or any
            # absolute path is refused so it cannot bypass the allowlist.
            if command.startswith("./") and command[2:] in case_scripts:
                continue
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="unknown_workflow_command",
                message=(
                    f"Workflow command {command!r} is an explicit path; only "
                    "adapter-declared case scripts may be given as a path."
                ),
                field=step_id,
            ))
            continue
        if _is_authorized(command, driver_context):
            if command in _MPI_LAUNCHERS:
                payload = _unwrap_mpi_program(tuple(step.get("args", ()) or ()))
                if payload is not None and not _is_authorized(payload, driver_context):
                    diagnostics.append(WorkflowDiagnostic(
                        level="error",
                        code="unauthorized_mpi_payload",
                        message=(
                            f"step {step_id or '<unknown>'!r} runs {payload!r} under "
                            "an MPI launcher, and that program is not in this "
                            "plugin's authorized command set"
                        ),
                        field=f"{step_id}.args" if step_id else "args",
                    ))
            continue
        manifest = utilities.get(command)
        if manifest is not None:
            # Present but declares no ``produces``: _is_authorized already
            # decided this command is not authorized on that basis.
            diagnostics.append(WorkflowDiagnostic(
                level="error",
                code="utility_without_produces",
                message=f"Utility {command!r} has no authoritative produces entries.",
                field=step_id,
            ))
            continue
        diagnostics.append(WorkflowDiagnostic(
            level="error",
            code="unknown_workflow_command",
            message=(
                f"Workflow command {command!r} is not a declared core, environment, "
                "plugin, case-script, or utility command."
            ),
            field=step_id,
        ))
    return tuple(diagnostics)
