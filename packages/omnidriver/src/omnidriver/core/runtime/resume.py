"""Bind persisted checkpoints to the workflow and observed input evidence.

The snapshot describes a checkpoint, not a build attestation; state without evidence cannot resume."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from .provenance import ProvenanceSnapshot, compare, snapshot_from_components
from .provenance_inputs import enumerate_case_inputs
from .reconciler import declared_instance_names, reconcile_artifacts
from .workflow_state import WorkflowRunState, workflow_digest
from .models import DataArtifact

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _environment_identity(environment: Mapping[str, str], driver_context: DriverContext) -> dict:
    """What a replay must find unchanged in the environment: the stack's supplied variables, less locations, and the declared launcher.

    The commands a run uses are identified by their resolved paths and digests
    in the case inputs, so ``PATH`` itself, a sourced file's location and the
    folders prepended to ``PATH`` are left out. Values are
    stored as digests, so a refusal can name a variable without a secret
    being saved.
    """
    from ..environment_connection import stack_connection

    connection, _ = stack_connection(driver_context)
    located = {connection.source, *connection.path_prepend}
    names = sorted(
        variable.name for variable in connection.supplied
        if not variable.locates and variable.name not in located
    )
    identity: dict = {
        "variables": {name: _digest(environment[name]) if name in environment else None for name in names},
    }
    if connection.mpi_launcher is not None:
        path = shutil.which(connection.mpi_launcher, path=environment.get("PATH"))
        identity["launcher"] = {"path": path, "real_path": str(Path(path).resolve()) if path else None}
    return identity


def checkpoint_snapshot(case_root: Path, workflow_dag: dict, driver_context: DriverContext,
                        env: Mapping[str, str] | None) -> dict:
    """Build the identity a resumed run's evidence is compared against."""
    environment = dict(os.environ if env is None else env)
    # Full identity, not provider_identity.STACK_IDENTITY_COMPARISON_KEYS: resuming replays a
    # specific prior attempt, so an import-path or environment change must force a fresh run
    # even though it wouldn't count as a "different stack" for plan/run/compare binding.
    identity = {
        **driver_context.identity.to_json(),
        "environment": _environment_identity(environment, driver_context),
    }
    snapshot = snapshot_from_components(
        enumerate_case_inputs(case_root, workflow_dag=workflow_dag,
                              driver_context=driver_context, env=environment),
        workflow_digest=workflow_digest(workflow_dag), plugin_identity=identity,
    )
    return json.loads(snapshot.to_json())


def _changed_names(before: Mapping, after: Mapping) -> list[str]:
    """The identity entries that differ: each environment variable by name, every other entry by its key."""
    names = []
    for key in sorted({*before, *after}):
        if before.get(key) == after.get(key):
            continue
        if key == "environment":
            old, new = before.get(key) or {}, after.get(key) or {}
            old_vars, new_vars = old.get("variables", {}), new.get("variables", {})
            names += [
                f"environment variable {name}" for name in sorted({*old_vars, *new_vars})
                if old_vars.get(name) != new_vars.get(name)
            ]
            if old.get("launcher") != new.get("launcher"):
                names.append("environment launcher")
        else:
            names.append(f"plugin {key}")
    return names


def validate_resume(state: WorkflowRunState, workflow_dag: dict, *, case_root: Path,
                    driver_context: DriverContext | None, env: Mapping[str, str] | None,
                    expected_artifacts: tuple[DataArtifact, ...] = ()) -> None:
    """Refuse reuse unless checkpoint identity and completed outputs still hold.

    Checks continued presence of required artifacts only; freshness is
    enforced at execution time, not here.
    """
    if state.workflow_digest != workflow_digest(workflow_dag):
        raise ValueError("Saved workflow identity is missing or changed; create a fresh run instead of reusing this state")
    expected = {str(step["id"]): step for step in workflow_dag["steps"]}
    actual = {step.step_id: step for step in state.steps}
    if len(actual) != len(state.steps) or set(actual) != set(expected):
        raise ValueError("Saved workflow steps do not match the current DAG")
    completed = {step.step_id for step in state.steps if step.status == "completed"}
    if set(state.completed_steps) != completed or len(state.completed_steps) != len(completed):
        raise ValueError("Saved completed-step list is inconsistent")
    if state.status == "completed" and (completed != set(expected) or state.current_step_id is not None):
        raise ValueError("Saved workflow claims completion without completing every step")
    if state.current_step_id is not None and state.current_step_id not in actual:
        raise ValueError("Saved current step is not in the DAG")
    for name, step in actual.items():
        spec = expected[name]
        if (step.command, step.args, step.cwd) != (
            str(spec["command"]), tuple(str(arg) for arg in spec.get("args", ())), str(spec.get("cwd", "."))
        ):
            raise ValueError(f"Saved command for step {name!r} differs from the current DAG")
        if step.status == "completed" and not set(spec.get("depends_on", ())).issubset(completed):
            raise ValueError(f"Saved completed step {name!r} has incomplete dependencies")
    # A zero-budget checkpoint has not consumed inputs and may start normally.
    if all(step.attempt == 0 and step.status == "pending" for step in state.steps):
        return
    if driver_context is None or state.resume_snapshot is None:
        raise ValueError("Saved workflow has no input evidence; create a fresh run")
    before = ProvenanceSnapshot.from_json(json.dumps(state.resume_snapshot))
    after = ProvenanceSnapshot.from_json(json.dumps(checkpoint_snapshot(case_root, workflow_dag, driver_context, env)))
    if not before.is_complete or not after.is_complete:
        raise ValueError("Saved workflow cannot resume with incomplete or metadata-only input evidence")
    differences = compare(before, after)
    if before.schema_version != after.schema_version or differences:
        changed = [
            diff.path if diff.kind != "plugin"
            else ", ".join(_changed_names(before.plugin_identity, after.plugin_identity))
            for diff in differences
        ]
        raise ValueError(
            f"Saved workflow input evidence changed ({', '.join(changed) or 'fingerprint policy'}); "
            "create a fresh run"
        )
    if state.status == "completed":
        report = reconcile_artifacts(
            case_root,
            expected_artifacts,
            instance_names=declared_instance_names(
                case_root, driver_context=driver_context,
            ),
        )
        missing = [
            entry["artifact_id"]
            for entry in report.artifacts
            if not entry["optional"] and entry["status"] != "matched"
        ]
        if missing:
            raise ValueError(
                "Saved workflow required outputs are missing "
                f"({', '.join(missing)}); create a fresh run instead of reusing this state"
            )
