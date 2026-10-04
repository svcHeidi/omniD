from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .core.runtime.failure_context import build_failure_context
from .core.runtime.launch_readiness import is_execution_successful, is_launchable
from .core.runtime.remediation import build_candidate_remediations
from .core.runtime.process_control import clear_stop_request, install_signal_handlers
from .core.runtime.workflow_runner import _step_state_by_id, run_workflow_step, settle_interrupted_steps
from .core.runtime.workflow_orchestrator import run_workflow
from .core.runtime.workflow_state import workflow_state_from_json
from .core.runtime.case_records import (
    CASE_RECORD_FILENAME,
    build_standalone_case_record,
    write_case_record,
)
from .core.runtime.workflow_orchestrator import STATE_FILENAME
from .core.case_transaction import CaseTransactionError, pending_transaction, recover_case_transaction
from .core.environment_connection import load_environment
from .core.runtime.sweep_runner import sweep_plan, sweep_run
from omnidriver.core.introspection import describe_entry
from omnidriver.core.planning_types import diagnostic
from omnidriver.core.provider_identity import stack_identity_mismatch
from omnidriver.core.specs.paths import SCRATCH_ENV_VAR, default_sweep_output_dir, resolve_scratch_root
from omnidriver.core.strict_planning import _utility_produces_by_command, strict_plan
from .core.runtime.run_document_exec import build_execution_inputs, load_run_document, _allowed_runs_root
from .core.runtime.fresh import ensure_fresh_output_dir
from .core.runtime.attempt_lease import (
    ATTEMPT_LOCK_FILENAME,
    ATTEMPT_LOCK_GUARD_FILENAME,
    AttemptLeaseError,
    acquire_attempt_lease,
    acquire_case_lease,
)
from .core.runtime.execution_context import (
    ReplannedExecution as _ReplannedExecution,
    StepExecutionContext as _ExecutionContext,
)
from .core.sweep.sweep_expansion import SweepValidationError
from .core.tutorial_records import PARALLEL_STUDY_NAME, TutorialRecordError, case_folder_record


if TYPE_CHECKING:
    from .core.plugin_interface import DriverContext


def _step_payload(
    *,
    status: str,
    entry: str,
    step: str,
    workflow_state_path: Path,
    workflow_state: dict,
    exit_code: int | None = None,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
    error: str | None = None,
) -> dict:
    payload = {
        "status": status,
        "entry": entry,
        "step": step,
        "exit_code": exit_code,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "workflow_state_path": str(workflow_state_path),
        "workflow_state": workflow_state,
    }
    if error is not None:
        payload["error"] = error
    return payload


def _terminal_status_label(workflow_status: str) -> str:
    """Derived from workflow status, never a subprocess exit code."""
    return "ok" if is_execution_successful(workflow_status) else "failed"


def _refuse_environment_errors(context: _ExecutionContext, *, action: str) -> int | None:
    # Structure was validated when the context was built, so only the
    # environment and coverage halves of is_launchable apply here.
    # `simulation_audit` must be threaded through, or a required check
    # reported `unavailable` could never block.
    readiness = is_launchable(
        plan_status="ok",
        environment_diagnostics=context.environment_diagnostics,
        simulation_audit=context.simulation_audit,
    )
    if readiness.environment_ok and readiness.coverage_ok:
        return None
    payload = {
        "status": "failed",
        "entry": context.entry_label,
        "action": action,
        "error": (
            "Execution environment preflight failed."
            if not readiness.environment_ok
            else "A required check could not run; dispatch refused."
        ),
        "environment_diagnostics": [asdict(diagnostic) for diagnostic in context.environment_diagnostics],
    }
    if not readiness.coverage_ok:
        payload["blocking_reason"] = readiness.blocking_reason
    if context.source_path is not None:
        payload["run_document"] = context.source_path
    print(json.dumps(payload, indent=2))
    return 1


def _attach_failure_context(payload: dict, state, step_id: str | None, *, tail_lines: int) -> None:
    """Add a failure_context bundle to ``payload`` when the step failed; never persisted to workflow_state.json."""
    if step_id is None:
        return
    step_state = _step_state_by_id(state, step_id)
    if step_state.status == "failed":
        fc = build_failure_context(step_state, max_lines=tail_lines)
        fc["candidate_remediations"] = [
            hint.to_json() for hint in build_candidate_remediations(fc)
        ]
        payload["failure_context"] = fc


def _execute_step(
    *,
    entry_label: str,
    step_id: str,
    workflow_dag: dict,
    planned_state,
    case_root: Path,
    output_dir: Path,
    expected_artifacts,
    tail_lines: int,
    execution_env: dict[str, str] | None = None,
    apply_path: str | None = None,
    driver_context: DriverContext | None = None,
    apply_study: Callable[[dict], tuple[dict, ...]] | None = None,
    replan_after_mutation: Callable[[], _ReplannedExecution] | None = None,
) -> int:
    """CLI JSON adapter over the structured core step executor."""
    from .core.runtime.step_execution import execute_step_owned

    study = None
    if apply_path is not None:
        try:
            study = json.loads(Path(apply_path).read_text())
            if not isinstance(study, dict):
                raise ValueError("--apply must be a JSON object of 'document:key' patches")
        except (OSError, ValueError) as exc:
            print(json.dumps({
                "status": "failed",
                "entry": entry_label,
                "step": step_id,
                "error": f"--apply rejected: {exc}",
            }, indent=2))
            return 1

    context = _ExecutionContext(
        entry_label=entry_label,
        workflow_dag=workflow_dag,
        planned_state=planned_state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=tuple(expected_artifacts or ()),
        execution_env=execution_env,
        driver_context=driver_context,
        apply_study=apply_study,
        replan_after_mutation=replan_after_mutation,
    )
    try:
        result = execute_step_owned(
            context,
            step_id=step_id,
            study=study,
            tail_lines=tail_lines,
            run_step=run_workflow_step,
        )
    except Exception as exc:
        prefix = "--apply rejected: " if apply_path is not None else ""
        payload = {
            "status": "failed",
            "entry": entry_label,
            "step": step_id,
            "error": f"{prefix}{exc}",
        }
        state_path = output_dir / STATE_FILENAME
        if state_path.exists():
            payload["workflow_state_path"] = str(state_path)
        print(json.dumps(payload, indent=2))
        return 1
    payload = dict(result.payload)
    if result.status != "rejected":
        payload["artifact_reconciliation"] = _reconciliation_payload(
            case_root, expected_artifacts, driver_context=driver_context,
        )
    print(json.dumps(payload, indent=2))
    return 0 if result.status == "succeeded" else 1


def _reconciliation_payload(case_root: Path, expected_artifacts, *, driver_context=None) -> dict:
    """Predicted artifacts against files on disk: path, size and sha256 only."""
    from .core.runtime.reconciler import declared_instance_names, reconcile_artifacts

    return reconcile_artifacts(
        case_root,
        expected_artifacts or (),
        instance_names=declared_instance_names(
            case_root, driver_context=driver_context,
        ),
    ).to_json()


def _execute_run(
    *,
    entry_label: str,
    workflow_dag: dict,
    planned_state,
    case_root: Path,
    output_dir: Path,
    expected_artifacts,
    tail_lines: int,
    setup_root: Path | None = None,
    execution_env: dict[str, str] | None = None,
    max_total_attempts: int | None = None,
    driver_context: DriverContext | None = None,
) -> int:
    """Run a workflow to completion and print the JSON payload; refuses to auto-resume a terminally failed saved state (use action=step)."""
    state_path = output_dir / STATE_FILENAME
    workflow_state = planned_state
    replayed = False
    if state_path.exists():
        try:
            workflow_state = settle_interrupted_steps(
                workflow_state_from_json(json.loads(state_path.read_text())), state_path,
            )
            from .core.runtime.resume import validate_resume

            validate_resume(workflow_state, workflow_dag, case_root=case_root,
                            driver_context=driver_context, env=execution_env,
                            expected_artifacts=tuple(expected_artifacts or ()))
            replayed = workflow_state.status == "completed"
        except Exception as exc:
            print(json.dumps({
                "status": "failed",
                "entry": entry_label,
                "error": f"Could not read existing workflow state: {exc}",
                "workflow_state_path": str(state_path),
            }, indent=2))
            return 1
    if workflow_state.status == "failed":
        print(json.dumps({
            "status": "failed",
            "entry": entry_label,
            "error": "workflow_state is failed; use action=step to rerun a failed step explicitly",
            "workflow_state_path": str(state_path),
            "workflow_state": workflow_state.to_json(),
        }, indent=2))
        return 1
    try:
        outcome = run_workflow(
            workflow_dag,
            workflow_state,
            case_root=case_root,
            output_dir=output_dir,
            expected_artifacts=expected_artifacts,
            state_path=state_path,
            env=execution_env,
            max_total_attempts=max_total_attempts,
            driver_context=driver_context,
            leases_held=True,
        )
    except Exception as exc:
        try:
            error_state = workflow_state_from_json(json.loads(state_path.read_text()))
        except Exception:
            error_state = workflow_state
        print(json.dumps(_step_payload(
            status="failed",
            entry=entry_label,
            step=error_state.current_step_id or workflow_state.current_step_id,
            workflow_state_path=state_path,
            workflow_state=error_state.to_json(),
            error=str(exc),
        ), indent=2))
        return 1
    workflow_state = outcome.state
    results = list(outcome.steps)
    status = _terminal_status_label(workflow_state.status)
    payload = {
        "status": status,
        "entry": entry_label,
        "steps": results,
        "workflow_state_path": str(state_path),
        "workflow_state": workflow_state.to_json(),
    }
    if replayed:
        payload["replayed"] = True
    if workflow_state.status == "pending" and workflow_state.current_step_id is None:
        payload["error"] = "workflow_state is pending but has no current_step_id"
    elif workflow_state.status == "pending" and max_total_attempts is not None:
        payload["error"] = "maximum total step attempts reached; workflow remains incomplete"
    payload["artifact_reconciliation"] = _reconciliation_payload(
        case_root, expected_artifacts, driver_context=driver_context,
    )
    case_record = build_standalone_case_record(
        entry=entry_label, case_root=case_root, setup_root=setup_root, output_dir=output_dir,
    )
    case_record_path = output_dir / CASE_RECORD_FILENAME
    write_case_record(case_record_path, case_record)
    payload["case_record_path"] = str(case_record_path)
    _attach_failure_context(payload, workflow_state, workflow_state.failed_step_id, tail_lines=tail_lines)
    print(json.dumps(payload, indent=2))
    return 0 if status == "ok" else 1


def _context_from_run_document(args, driver_context) -> _ExecutionContext | None:
    """Load + validate an agent-authored RunDocument into executor inputs."""
    try:
        run_doc = load_run_document(args.run_document)
    except Exception as exc:
        # A load failure never reached validation, so it has no other
        # diagnostic -- synthesize one here in the one canonical shape an
        # agent parsing `diagnostics` can rely on.
        print(json.dumps({
            "status": "failed",
            "error": f"Could not load run document: {exc}",
            "run_document": args.run_document,
            "diagnostics": [asdict(diagnostic(
                "error", "run_document_unreadable", str(exc), source="cli",
            ))],
        }, indent=2))
        return None
    if run_doc.plugin is not None:
        planned = run_doc.plugin
        selected = driver_context.identity.to_json()
        # See `provider_identity.stack_identity_mismatch` for what is compared
        # and why; the same comparison is shared with `run_document_exec.py`
        # and `quantities.comparison`.
        mismatched = stack_identity_mismatch(planned, selected)
        if mismatched:
            print(json.dumps({
                "status": "failed",
                "run_document": args.run_document,
                "error": (
                    "RunDocument plugin does not match the selected plugin: "
                    + ", ".join(mismatched)
                ),
                "planned_plugin": planned,
                "selected_plugin": selected,
            }, indent=2))
            return None
    execution_env = load_environment(driver_context, args.environment_source)
    inputs, diagnostics = build_execution_inputs(
        run_doc,
        utility_produces=_utility_produces_by_command(driver_context),
        driver_context=driver_context,
        execution_env=execution_env,
    )
    if inputs is None:
        print(json.dumps({
            "status": "failed",
            "run_document": args.run_document,
            "diagnostics": [asdict(d) for d in diagnostics],
        }, indent=2))
        return None
    record = driver_context.stack.call("get_tutorial_records").get(run_doc.name)
    if record is not None and args.apply is None:
        from .core.runtime.record_execution import refuse_a_case_that_breaks_a_rule

        try:
            refuse_a_case_that_breaks_a_rule(
                record, inputs.case_root, driver_context,
                then="; patch it with step --apply, or plan again, before it runs",
            )
        except TutorialRecordError as exc:
            print(json.dumps({"status": "failed", "run_document": args.run_document, "error": str(exc)}, indent=2))
            return None
    setup_root_raw = (run_doc.launch or {}).get("setupRoot")

    def replan_after_mutation() -> _ReplannedExecution:
        current_document = load_run_document(args.run_document)
        current_inputs, current_diagnostics = build_execution_inputs(
            current_document,
            utility_produces=_utility_produces_by_command(driver_context),
            driver_context=driver_context,
            execution_env=execution_env,
        )
        if current_inputs is None:
            raise ValueError(
                "replanned RunDocument is invalid: "
                + json.dumps([asdict(d) for d in current_diagnostics], sort_keys=True)
            )
        if (
            current_inputs.case_root.resolve() != inputs.case_root.resolve()
            or current_inputs.output_dir.resolve() != inputs.output_dir.resolve()
        ):
            raise ValueError("replanned RunDocument changed its case or output identity")
        return _ReplannedExecution(
            workflow_dag=current_inputs.workflow_dag,
            planned_state=current_inputs.workflow_state,
            expected_artifacts=current_inputs.expected_artifacts,
        )

    def apply_study(study: dict, check: Callable[[], None]) -> tuple[dict, ...]:
        from .core.runtime.record_execution import apply_record_study

        records = driver_context.stack.call("get_tutorial_records")
        record = records.get(run_doc.name)
        if record is None:
            raise ValueError(f"run document {run_doc.name!r} is not a tutorial record of this plugin")
        return apply_record_study(
            record, case_root=inputs.case_root, study=study,
            driver_context=driver_context, execution_env=execution_env, check=check,
        )

    return _ExecutionContext(
        entry_label=run_doc.name,
        workflow_dag=inputs.workflow_dag,
        planned_state=inputs.workflow_state,
        case_root=inputs.case_root,
        output_dir=inputs.output_dir,
        expected_artifacts=inputs.expected_artifacts,
        setup_root=Path(setup_root_raw) if setup_root_raw else None,
        environment_diagnostics=driver_context.stack.call(
            "get_environment_diagnostics",
            inputs.workflow_dag,
            environment_source=args.environment_source,
            driver_context=driver_context,
        ),
        simulation_audit=inputs.simulation_audit,
        execution_env=execution_env,
        driver_context=driver_context,
        source_path=args.run_document,
        apply_study=apply_study,
        replan_after_mutation=replan_after_mutation,
    )


def _context_from_entry(
    *,
    selected_entry,
    overrides: dict | None,
    environment_source: str | None,
    driver_context,
    allow_unresolved_configuration: bool = False,
    scratch_dir: str | None = None,
    cli_study: dict | None = None,
    inputs: dict | None = None,
) -> tuple[_ExecutionContext | None, int]:
    label = getattr(selected_entry, "name", selected_entry)

    def plan():
        return strict_plan(
            selected_entry,
            overrides=overrides,
            environment_source=environment_source,
            allow_unresolved_configuration=allow_unresolved_configuration,
            scratch_root=scratch_dir,
            cli_study=cli_study,
            inputs=inputs,
            driver_context=driver_context,
        )

    try:
        report = plan()
    except TutorialRecordError as exc:
        print(json.dumps({
            "status": "failed",
            "entry": label,
            "error": str(exc),
        }, indent=2))
        return None, 1
    readiness = is_launchable(
        plan_status=report.status,
        environment_diagnostics=report.environment_diagnostics,
    )
    if not readiness.structural_ok:
        print(json.dumps(report.to_json(), indent=2))
        return None, 1
    if report.workflow_dag is None or report.workflow_state is None:
        print(json.dumps({
            "status": "failed",
            "error": "strict plan did not produce workflow_dag and workflow_state",
        }, indent=2))
        return None, 1
    execution_env = load_environment(driver_context, environment_source)

    return (
        _ExecutionContext(
            entry_label=label,
            workflow_dag=report.workflow_dag,
            planned_state=report.workflow_state,
            case_root=Path(report.launch["case_root"]),
            output_dir=Path(report.launch["output_dir"]),
            expected_artifacts=report.expected_artifacts,
            setup_root=Path(report.launch["setup_root"]),
            environment_diagnostics=report.environment_diagnostics,
            simulation_audit=report.simulation_audit,
            execution_env=execution_env,
            driver_context=driver_context,
        ),
        0,
    )


def _dispatch_context(args, context: _ExecutionContext) -> int:
    blocked = _refuse_environment_errors(context, action=args.action)
    if blocked is not None:
        return blocked
    try:
        with acquire_case_lease(context.case_root):
            return _dispatch_context_owned(args, context)
    except AttemptLeaseError as exc:
        print(json.dumps({
            "status": "failed",
            "entry": context.entry_label,
            "action": args.action,
            "error": str(exc),
        }, indent=2))
        return 1


def _dispatch_context_owned(args, context: _ExecutionContext) -> int:
    output_existed = context.output_dir.exists()
    with acquire_attempt_lease(context.output_dir):
        if args.fresh and output_existed:
            if context.case_root.resolve().is_relative_to(context.output_dir.resolve()):
                print(json.dumps({
                    "status": "failed",
                    "entry": context.entry_label,
                    "action": args.action,
                    "error": (
                        f"--fresh would delete the case itself: its output directory "
                        f"{context.output_dir} holds the case. Plan again "
                        "(plan --strict --entry) to restage it"
                    ),
                }, indent=2))
                return 1
            fresh_error = ensure_fresh_output_dir(
                context.output_dir,
                fresh=True,
                allowed_root=_allowed_runs_root(),
                # Use attempt_lease.py's own constants, not literals here, so
                # a changed ATTEMPT_LOCK_FILENAME can't let --fresh delete the
                # live lease out from under itself.
                preserve_names=frozenset({
                    ATTEMPT_LOCK_FILENAME,
                    ATTEMPT_LOCK_GUARD_FILENAME,
                }),
            )
            if fresh_error is not None:
                print(json.dumps({
                    "status": "failed",
                    "entry": context.entry_label,
                    "action": args.action,
                    "error": fresh_error,
                }, indent=2))
                return 1
        pending = pending_transaction(context.case_root)
        if pending is not None:
            print(json.dumps({
                "status": "failed",
                "entry": context.entry_label,
                "action": args.action,
                "error": (
                    f"case transaction {pending.get('transaction_id')} was interrupted; "
                    f"run `omnidriver recover --case-root {context.case_root}` first"
                ),
            }, indent=2))
            return 1
        if args.action == "step":
            return _execute_step(
                entry_label=context.entry_label,
                step_id=args.step,
                workflow_dag=context.workflow_dag,
                planned_state=context.planned_state,
                case_root=context.case_root,
                output_dir=context.output_dir,
                expected_artifacts=context.expected_artifacts,
                tail_lines=args.tail_lines,
                execution_env=context.execution_env,
                apply_path=args.apply,
                driver_context=context.driver_context,
                apply_study=context.apply_study,
                replan_after_mutation=context.replan_after_mutation,
            )
        return _execute_run(
            entry_label=context.entry_label,
            workflow_dag=context.workflow_dag,
            planned_state=context.planned_state,
            case_root=context.case_root,
            output_dir=context.output_dir,
            expected_artifacts=context.expected_artifacts,
            setup_root=context.setup_root,
            tail_lines=args.tail_lines,
            execution_env=context.execution_env,
            max_total_attempts=args.max_total_attempts,
            driver_context=context.driver_context,
        )


def _run_document_dispatch(args, driver_context) -> int:
    """Execute a validated RunDocument through the shared strict executor."""
    context = _context_from_run_document(args, driver_context)
    if context is None:
        return 1
    return _dispatch_context(args, context)


def _recover(args) -> int:
    """Restore the before-images of an interrupted case transaction."""
    case_root = Path(args.case_root).resolve()
    try:
        recovered = recover_case_transaction(case_root)
    except CaseTransactionError as exc:
        print(json.dumps({
            "status": "failed",
            "action": "recover",
            "case_root": str(case_root),
            "error": str(exc),
        }, indent=2))
        return 1
    print(json.dumps({
        "status": "ok",
        "action": "recover",
        "case_root": str(case_root),
        "transaction_id": recovered.transaction_id if recovered else None,
    }, indent=2))
    return 0


def _compare_quantities(args) -> int:
    """``compare``: exit 0 once the report is written, whatever its status; 1 on a refusal."""
    from .core.quantities import QuantityComparisonError, run_quantity_comparison

    try:
        report = run_quantity_comparison(Path(args.comparison_request), Path(args.report))
    except QuantityComparisonError as exc:
        print(json.dumps({"status": "failed", "action": "compare", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


def resolve_cases_root(explicit: str | Path | None = None) -> Path:
    """Where to look for cases, resolved at the public edge only:
    explicit, then OMNIDRIVER_CASES_ROOT, then the current working directory.
    Core itself resolves nothing.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    from_env = os.environ.get("OMNIDRIVER_CASES_ROOT")
    if from_env:
        return Path(from_env).expanduser()
    return Path.cwd()


def _parallel_value(text: str) -> int:
    """``--parallel N``: N as the integer the study value would hold."""
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--parallel takes an integer, got {text!r}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Simulation experiment automation driver. `omnidriver build --help` builds a case "
            "from a solver's catalogue when there is no native case."
        ),
    )
    parser.add_argument(
        "action",
        choices=[
            "describe", "catalog", "env", "scan", "check", "plan", "step", "run", "recover", "sweep-plan",
            "sweep-run", "compare",
        ],
        help="Pipeline stage to execute",
    )
    parser.add_argument(
        "--plugin",
        help=(
            "Plugin to drive: an installed plugin id from the "
            "'omnidriver.plugins' entry-point group, or a trusted "
            "local-development import target (module.path:PluginClass); a "
            "colon always selects the import form. Either form executes the "
            "plugin's Python code. For a solver with no repository; "
            "otherwise the repository's omnidriver.toml names the plugin, "
            "and --plugin, when given too, must select the same stack."
        ),
    )
    parser.add_argument(
        "--repo",
        metavar="DIR",
        help=(
            "A solver repository: DIR holds an omnidriver.toml naming its "
            "plugin, tutorials, C++ source and helper scripts. Its tutorials "
            "folder is the cases root. A --cases-root (or "
            "$OMNIDRIVER_CASES_ROOT) that is a repository's tutorials folder "
            "selects the repository the same way. Never searched for."
        ),
    )
    parser.add_argument(
        "--entry",
        required=False,
        help=(
            "The tutorial record to describe, plan or run: a name the selected "
            "stack registers (`describe` lists them)."
        ),
    )
    parser.add_argument(
        "--case",
        metavar="DIR",
        help=(
            "Run a case folder that is not a record, in place of --entry: an "
            "ad hoc record of one step, the stack's declared case entrypoint, "
            "staged from DIR, which is never written. Refused where the "
            "stack declares no entrypoint."
        ),
    )
    parser.add_argument(
        "--run-document",
        help=(
            "Path to a RunDocument v3 JSON file. With action=run/step, "
            "executes the document's workflowDag instead of regenerating "
            "the plan from --entry. Mutually exclusive with --entry/--case. "
            "Given neither --plugin nor --repo, the stack is the installed "
            "plugin (and repository) the plan recorded in the document's "
            "launch command."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="For action=plan/step/run, fail on incomplete machine-readable coverage.",
    )
    parser.add_argument(
        "--allow-unresolved-configuration",
        action="store_true",
        help=(
            "Permit only an explicitly exploratory strict plan/run when declared "
            "configuration closure is unresolved, execution-required, or its "
            "evaluator is unavailable. Unknown evidence states still fail."
        ),
    )
    parser.add_argument(
        "--environment-source",
        dest="environment_source",
        default=None,
        help=(
            "An opaque value handed to the active plugin's environment hooks "
            "for strict plan/step/run; core never reads it. What it names is "
            "the plugin's own business (a script to source, or nothing). "
            "Absent, the plugin uses whatever its tool's ambient environment is."
        ),
    )
    parser.add_argument(
        "--parallel",
        nargs="?",
        const=True,
        default=None,
        type=_parallel_value,
        metavar="N",
        help=(
            "For describe, plan/step/run --strict, sweep-plan/sweep-run: "
            "run the record's solve step in the composed "
            "stack's parallel form -- the same request as the study value "
            "'parallel', from another source; one that disagrees with the "
            "study's is refused. Absent: serial. '--parallel' leaves the "
            "process count to the solver layer, which reads it from the "
            "case or the scheduler's allocation (SLURM_NTASKS); '--parallel "
            "N' states N, which a layer whose case states a count must find "
            "equal to it. Refused "
            "by name where the stack has no parallel form, or where N, the "
            "case and the allocation disagree."
        ),
    )
    parser.add_argument(
        "--input",
        dest="inputs",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help=(
            "For describe, plan/step/run --strict, sweep-plan/sweep-run: "
            "supply one of the record's declared inputs -- data "
            "outside its native case folder (a patient anatomy bundle, a "
            "shared mesh) that has no ambient location. Repeatable. A record "
            "with no native location for an input refuses to plan/run "
            "without it, by name; describe never refuses, and lists each "
            "input's supplied status instead."
        ),
    )
    parser.add_argument(
        "--step",
        help="Workflow step id to execute when action=step.",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=200,
        help="For action=step/run --strict, number of log lines to include in failure_context (default 200).",
    )
    parser.add_argument(
        "--apply",
        metavar="PATCHES_JSON",
        help=(
            "action=step with --run-document only: edit the staged case with a "
            "JSON object of 'document:key' patches, the same a study takes, "
            "then rerun the step. The step must be pending or failed with its "
            "dependencies completed, or nothing is written. An edit the "
            "stack's rules refuse, or whose replan changes the workflow, is "
            "rolled back; patches that change nothing do not rerun a step that "
            "has run (status 'unchanged', exit 1)."
        ),
    )
    parser.add_argument(
        "--cases-root",
        help=(
            "Path to the tutorials folder. Defaults to $OMNIDRIVER_CASES_ROOT, "
            "then the current working directory."
        ),
    )
    parser.add_argument(
        "--case-root",
        help="For action=recover: the case directory whose interrupted transaction to restore.",
    )
    parser.add_argument(
        "--spec",
        help="Path to a sweep.json for action=sweep-plan/sweep-run.",
    )
    parser.add_argument(
        "--output-dir",
        help=(
            "Output directory for action=sweep-plan/sweep-run. Defaults to "
            "<scratch>/sweeps/<spec-name>, <scratch> being --scratch-dir or "
            "$OMNIDRIVER_SCRATCH_DIR (refused when neither is supplied); "
            "generated cases and logs never belong under tutorials/."
        ),
    )
    parser.add_argument(
        "--scratch-dir",
        help=(
            "Writable directory for disposable working data: a tutorial "
            "record's staged case (records/<name>), a run's staged case "
            "(runs/<name>), a sweep's default output (sweeps/<spec-name>). "
            "Overrides $OMNIDRIVER_SCRATCH_DIR. There is no default: an "
            "operation that stages refuses when neither is supplied, and a "
            "scratch dir inside --cases-root is refused. Read only when an "
            "operation stages, so describe (which previews in a discarded "
            "temporary directory) never needs it."
        ),
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=200,
        help="Safety cap on expanded sweep case count (default 200).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "For action=step/run with --run-document, and sweep-run: delete the "
            "previous output before running, so the workflow executes as if no "
            "prior run existed. With --run-document it clears the run's output "
            "directory (refused where that directory holds the case, as it does "
            "for a record: plan again); with sweep-run it clears --output-dir, "
            "after the spec has been validated. Not valid with --entry/--case, "
            "which always restage. Refuses to delete the filesystem root, your "
            "home directory, a too-shallow path, a symlink, anything outside "
            "OMNIDRIVER_ALLOWED_RUNS_ROOT when set, or a directory with no "
            "omnidriver artifact (workflow_state.json, sweep_manifest.json or "
            "run_document.json) at its top level. No confirmation prompt."
        ),
    )
    parser.add_argument(
        "--max-total-attempts",
        type=int,
        default=None,
        help=(
            "For action=run: whole-run ceiling on step executions (retry-storm "
            "guard). Default: unbounded (only per-step max_attempts applies)."
        ),
    )
    parser.add_argument(
        "--case-timeout-s",
        type=float,
        default=None,
        help=(
            "For action=sweep-run: wall-clock timeout per case subprocess; a case "
            "that exceeds it is marked failed and the sweep continues. Default: none."
        ),
    )
    parser.add_argument(
        "--document",
        help=(
            "For action=catalog: list only this document's entries, as the "
            "record's key catalogue names it (e.g. constant/electroProperties)."
        ),
    )
    parser.add_argument(
        "--key",
        help=(
            "For action=catalog: list only the entries that list this key "
            "(a concrete key such as stim[0].start matches its stim[Int].start template)."
        ),
    )
    parser.add_argument(
        "--uncatalogued",
        action="store_true",
        help=(
            "For action=catalog: list every key the stack's C++ reads and its "
            "catalogue lacks, with the scanned type, default and source "
            "location (no --entry needed)."
        ),
    )
    parser.add_argument(
        "--unread",
        action="store_true",
        help=(
            "For action=catalog: list every catalogued key the stack's C++ no "
            "longer reads (setting one has no effect), with what is needed to "
            "retire or correct its entry (no --entry needed)."
        ),
    )
    parser.add_argument(
        "--record",
        help=(
            "For action=check: check only this record (default: every record that declares a "
            "conformance study)."
        ),
    )
    parser.add_argument(
        "--checks",
        help="For action=check: the conformance checks to run, comma-separated (default: C1 to C14).",
    )
    parser.add_argument(
        "--benchmarks",
        metavar="DIR",
        help="For action=check: the directory of benchmark references a record's quantity cites (C13, C14).",
    )
    parser.add_argument(
        "--regression",
        action="store_true",
        help=(
            "For action=check: also run each record's native regression script (the one its case-file "
            "rules name) in a copy of the native case under the scratch root."
        ),
    )
    parser.add_argument(
        "--comparison-request",
        help="For action=compare: an agent's quantity comparison request (JSON; schema omnidriver/schemas/quantity-comparison.schema.json).",
    )
    parser.add_argument(
        "--report",
        help="For action=compare: where to write the comparison report. Must not exist: a report is written once.",
    )

    return parser


_FLAG_ERRORS_BY_ACTION = {
    "catalog": (
        ("parallel", "--parallel is not valid with action=catalog"),
        ("inputs", "--input is not valid with action=catalog"),
    ),
}


def _validate_args(parser: argparse.ArgumentParser, args) -> None:
    for flag_name, message in _FLAG_ERRORS_BY_ACTION.get(args.action, ()):
        if getattr(args, flag_name):
            parser.error(message)
    if (args.document or args.key or args.uncatalogued or args.unread) and args.action != "catalog":
        parser.error("--document/--key/--uncatalogued/--unread are only valid with action=catalog")
    if (args.record or args.checks or args.benchmarks or args.regression) and args.action != "check":
        parser.error("--record/--checks/--benchmarks/--regression are only valid with action=check")
    if args.action == "check":
        if any((
            args.entry, args.case, args.run_document, args.spec, args.output_dir, args.strict,
            args.parallel is not None, args.step, args.apply is not None,
        )):
            parser.error(
                "action=check takes --plugin or --repo, --cases-root, --scratch-dir, --input, --record, "
                "--checks, --benchmarks and --regression only"
            )
    if args.uncatalogued and args.unread:
        parser.error("--uncatalogued and --unread are separate listings: pass one")
    if (args.uncatalogued or args.unread) and (args.entry or args.case or args.document or args.key):
        parser.error("--uncatalogued/--unread list the whole stack's C++ scan; they take no --entry/--case/--document/--key")
    if args.action not in {"plan", "step", "run"} and args.strict:
        parser.error("--strict is only valid with action=plan, action=step, or action=run")
    if args.allow_unresolved_configuration and args.action not in {"plan", "step", "run"}:
        parser.error(
            "--allow-unresolved-configuration is only valid with action=plan, action=step, or action=run"
        )
    if args.environment_source and args.action not in {"plan", "step", "run"}:
        parser.error(
            "--environment-source is only valid with action=plan, action=step, or action=run"
        )
    if args.action != "step" and args.step:
        parser.error("--step is only valid with action=step")
    if args.apply is not None and (args.action != "step" or not args.run_document):
        parser.error("--apply is only valid with action=step and --run-document: it edits an already staged case")
    if args.action not in {"step", "run"} and args.tail_lines != 200:
        parser.error("--tail-lines is only valid with action=step or action=run")
    if args.run_document and args.action not in {"run", "step"}:
        parser.error("--run-document is only valid with action=run or action=step")
    if args.repo and args.cases_root:
        parser.error("--repo supplies the cases root (its tutorials folder); --cases-root is not valid with it")
    if args.repo and args.action in {"recover", "compare"}:
        parser.error(f"--repo is not valid with action={args.action}")
    if args.entry and args.case:
        parser.error("--entry and --case are mutually exclusive")
    if args.run_document and (args.entry or args.case):
        parser.error("--run-document and --entry/--case are mutually exclusive")
    if args.run_document and args.cases_root:
        parser.error("--cases-root is not valid with --run-document")
    if args.case and args.cases_root:
        parser.error("--case names the folder itself; --cases-root is not valid with it")
    if args.case and args.action not in {"describe", "catalog", "plan", "step", "run"}:
        parser.error("--case is only valid with action=describe, catalog, plan, step or run")
    if args.parallel is not None and (
        args.run_document or args.action not in {"describe", "plan", "step", "run", "sweep-plan", "sweep-run"}
    ):
        parser.error(
            "--parallel is only valid where a tutorial record's run is planned: "
            "describe, plan/step/run with --entry/--case, sweep-plan, sweep-run"
        )
    if args.run_document and args.allow_unresolved_configuration:
        parser.error("--allow-unresolved-configuration requires --entry, not --run-document")
    if args.action in {"sweep-plan", "sweep-run"}:
        if args.entry:
            parser.error(f"--entry is not valid with action={args.action}; use --spec")
        if args.cases_root:
            parser.error(f"--cases-root is not valid with action={args.action}")
        if args.strict or args.run_document or args.step or args.apply is not None:
            parser.error(f"--strict/--run-document/--step/--apply are not valid with action={args.action}")
    if args.action in {"sweep-plan", "sweep-run"} and not args.spec:
        parser.error(f"action={args.action} requires --spec")
    if args.fresh and (args.entry or args.case):
        parser.error(
            "--fresh is not valid with --entry/--case: they always restage the case, replacing the "
            "previous one; use --fresh with --run-document or sweep-run"
        )
    if args.fresh and args.action not in {"step", "run", "sweep-run"}:
        parser.error("--fresh is only valid with action=step, action=run, or action=sweep-run")
    if args.max_cases != 200 and args.action not in {"sweep-plan", "sweep-run"}:
        parser.error("--max-cases is only valid with action=sweep-plan or action=sweep-run")
    if args.action not in {"sweep-plan", "sweep-run"} and (args.spec or args.output_dir):
        parser.error("--spec/--output-dir are only valid with action=sweep-plan or action=sweep-run")
    if args.action == "recover":
        if not args.case_root:
            parser.error("action=recover requires --case-root")
        if any((args.entry, args.case, args.run_document, args.cases_root, args.spec, args.output_dir)):
            parser.error(
                "--entry/--case/--run-document/--cases-root/--spec/--output-dir are not valid "
                "with action=recover"
            )
    elif args.case_root:
        parser.error("--case-root is only valid with action=recover")
    if args.action == "recover" and args.scratch_dir:
        parser.error("--scratch-dir is not valid with action=recover")
    if args.action == "compare":
        if not args.comparison_request or not args.report:
            parser.error("action=compare requires --comparison-request and --report")
        if any((args.entry, args.case, args.run_document, args.cases_root, args.spec, args.output_dir,
                args.plugin, args.repo, args.scratch_dir)):
            parser.error("--entry/--case/--run-document/--cases-root/--spec/--output-dir/--plugin/--repo/--scratch-dir "
                         "are not valid with action=compare: each run in the request names its own plugin and sweep")
    elif args.comparison_request or args.report:
        parser.error("--comparison-request/--report are only valid with action=compare")
    if args.action == "env" and any((
        args.entry, args.case, args.run_document, args.cases_root, args.spec, args.output_dir,
        args.scratch_dir, args.parallel is not None, args.inputs,
    )):
        parser.error("action=env takes only --plugin or --repo: it reports the stack's environment, not a run's")
    if args.action == "scan" and any((
        args.entry, args.case, args.run_document, args.cases_root, args.spec, args.output_dir,
        args.parallel is not None, args.inputs,
    )):
        parser.error("action=scan takes only --plugin or --repo, and --scratch-dir: it rescans the stack's C++ source")
    if not args.run_document and not args.entry and not args.case and not (args.uncatalogued or args.unread) and args.action not in {
        "recover", "sweep-plan", "sweep-run", "compare", "env", "scan", "check",
    }:
        parser.error("--entry or --case is required (or use --run-document with action=run/step)")


def _sweep_output_dir(args) -> str | Path | None:
    """``--output-dir``, else ``<scratch>/sweeps/<spec-name>`` (needed only when it is absent); ``None`` after a JSON refusal."""
    if args.output_dir:
        return args.output_dir
    try:
        return default_sweep_output_dir(args.spec, scratch_root=args.scratch_dir)
    except TutorialRecordError as exc:
        print(json.dumps({
            "status": "failed",
            "action": args.action,
            "spec": args.spec,
            "error": str(exc),
        }, indent=2))
        return None


def _sweep_refusal(args, exc: Exception) -> int:
    """A refusal of the sweep as a whole, printed as JSON; a per-case refusal is a ``materialization_error`` in the sweep report instead."""
    print(json.dumps({
        "status": "failed",
        "action": args.action,
        "spec": args.spec,
        "error": str(exc),
    }, indent=2))
    return 1


def _scan_or_uncatalogued(args, driver_context) -> int:
    """``scan`` rescans the stack's C++ into the scratch cache; ``catalog --uncatalogued`` lists what the C++ reads and the catalogue lacks."""
    from .core.catalog_query import cxx_evidence, scan_query

    try:
        cache_root = resolve_scratch_root(args.scratch_dir)
    except TutorialRecordError:
        if args.action == "scan":
            print(json.dumps({
                "status": "failed", "action": "scan",
                "error": "no scratch root was supplied: scan writes its cache there; pass "
                         "--scratch-dir <dir> or set OMNIDRIVER_SCRATCH_DIR",
            }, indent=2))
            return 1
        cache_root = None
    if args.action == "catalog":
        print(json.dumps(scan_query(driver_context, cache_root=cache_root, unread=args.unread), indent=2))
        return 0
    cxx = cxx_evidence(driver_context, os.environ, cache_root=cache_root, force=True)
    summary: dict = {
        "action": "scan",
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "cxx_source": cxx,
    }
    if cxx is None or not cxx["scanned"]:
        summary["status"] = "failed"
        summary["error"] = "the stack declares no C++ source" if cxx is None else cxx["reason"]
    else:
        cxx.pop("selector_values")
        for name in ("uncatalogued", "unresolved", "unread", "disagreements"):
            cxx[name] = len(cxx[name])
        summary["status"] = "ok"
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 1


def _check(args, driver_context, repository, cases_root: Path, inputs: dict[str, str]) -> int:
    """``check``: report only; the exit code is 0 whenever the checks ran."""
    from .conformance.report import check_report

    try:
        scratch_root = resolve_scratch_root(args.scratch_dir, cases_root=cases_root)
        report = check_report(
            driver_context, plugin=args.plugin or repository.plugin, cases_root=cases_root,
            scratch_root=scratch_root, records=[args.record] if args.record else [],
            check_ids=[name.strip() for name in (args.checks or "").split(",") if name.strip()],
            inputs=inputs, benchmarks=Path(args.benchmarks) if args.benchmarks else None,
            regression=args.regression,
        )
    except (TutorialRecordError, KeyError) as exc:
        print(json.dumps({"status": "failed", "action": "check", "error": str(exc.args[0] if exc.args else exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


def _adopt_run_document_stack(args) -> None:
    """With neither ``--plugin`` nor ``--repo``, take them from the command the run document was planned with.

    Only an installed plugin id is taken: a document never names Python to
    import (a ``module:Class`` selector must be passed explicitly).
    """
    if not args.run_document or args.plugin or args.repo:
        return
    try:
        command = json.loads(Path(args.run_document).read_text())["launch"]["command"]
    except (OSError, ValueError, KeyError, TypeError):
        return
    if not isinstance(command, list):
        return

    def after(flag: str) -> str | None:
        """The word that follows ``flag`` in the recorded command."""
        index = command.index(flag) + 1 if flag in command else len(command)
        return command[index] if index < len(command) else None

    plugin = after("--plugin")
    if isinstance(plugin, str) and ":" not in plugin:
        args.plugin, args.repo = plugin, after("--repo")


def _select_stack(parser: argparse.ArgumentParser, args):
    """The stack and the repository it came from (``--repo`` or a supplied cases root, never a search); ``--plugin`` and the repository must agree."""
    from .core.plugin_interface import load_plugin_context
    from .core.provider_identity import stack_identity_mismatch
    from .core.repository import RepositoryError, read_repository, repository_of_cases_root

    repository = None
    try:
        if args.repo:
            repository = read_repository(Path(args.repo).expanduser())
        elif args.action not in {"recover", "compare"}:
            supplied = args.cases_root or os.environ.get("OMNIDRIVER_CASES_ROOT")
            if supplied:
                repository = repository_of_cases_root(Path(supplied))
    except RepositoryError as exc:
        parser.error(str(exc))
    selector = args.plugin or (repository.plugin if repository is not None else None)
    if selector is None:
        parser.error(
            "no plugin was selected: pass --plugin, or --repo (or a --cases-root that is a "
            "repository's tutorials folder) whose omnidriver.toml names one"
        )
    try:
        context = load_plugin_context(selector)
        declared = load_plugin_context(repository.plugin) if repository is not None and args.plugin else None
    except Exception as exc:
        parser.error(f"Failed to load plugin {selector!r}: {exc}")
    if declared is not None:
        mismatch = stack_identity_mismatch(declared.identity.to_json(), context.identity.to_json())
        if mismatch:
            parser.error(
                f"--plugin {args.plugin!r} and {repository.root / 'omnidriver.toml'} "
                f"(plugin = {repository.plugin!r}) select different stacks ({', '.join(mismatch)})"
            )
    if repository is not None:
        from omnidriver.core.provider_stack import provider_profile

        for provider in context.providers:
            mapping = provider_profile(provider).cxx_mapping
            if mapping is None:
                continue
            if (repository.tutorials / mapping.source_root_relative).resolve() != repository.source:
                parser.error(
                    f"{repository.root / 'omnidriver.toml'} declares source = {repository.source}, but "
                    f"{provider.plugin_id} finds its C++ source at {mapping.source_root_relative!r} "
                    f"beside the tutorials folder {repository.tutorials}"
                )
            supplied_value = os.environ.get(mapping.source_root_variable)
            if supplied_value and Path(supplied_value).expanduser().resolve() != repository.tutorials:
                parser.error(
                    f"{mapping.source_root_variable}={supplied_value} disagrees with the tutorials "
                    f"folder {repository.tutorials} that {repository.root / 'omnidriver.toml'} declares"
                )
            os.environ[mapping.source_root_variable] = str(repository.tutorials)
        context = dataclasses.replace(context, repository=repository)
    return context, repository


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["build"]:
        from .core.case_build import main as build_main

        return build_main(argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    previous = os.environ.get(SCRATCH_ENV_VAR)
    previous_handlers = (
        install_signal_handlers() if args.action in {"step", "run", "sweep-run", "check"} else {}
    )
    if args.scratch_dir and args.action != "recover":
        # The one supplied scratch root, for the layers that cache a scan there.
        os.environ[SCRATCH_ENV_VAR] = str(Path(args.scratch_dir).expanduser())
    try:
        return _dispatch(parser, args)
    finally:
        for number, handler in previous_handlers.items():
            signal.signal(number, handler)
        clear_stop_request()
        if previous is None:
            os.environ.pop(SCRATCH_ENV_VAR, None)
        else:
            os.environ[SCRATCH_ENV_VAR] = previous


def _dispatch(parser: argparse.ArgumentParser, args) -> int:
    if args.action == "recover":
        return _recover(args)

    if args.action == "compare":
        return _compare_quantities(args)

    _adopt_run_document_stack(args)
    driver_context, repository = _select_stack(parser, args)

    if args.action == "env":
        from .core.environment_connection import environment_report

        report = environment_report(driver_context)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "ok" else 1

    if args.action == "scan" or args.uncatalogued or args.unread:
        return _scan_or_uncatalogued(args, driver_context)

    # The CLI's own study source, beside a sweep's `base`.
    cli_study = {PARALLEL_STUDY_NAME: args.parallel} if args.parallel is not None else {}
    # --input NAME=PATH, repeatable; never discovered (CLAUDE.md).
    cli_inputs: dict[str, str] = {}
    for raw in args.inputs:
        name, separator, path = raw.partition("=")
        if not separator or not name or not path:
            parser.error(f"--input {raw!r} must be NAME=PATH")
        if name in cli_inputs:
            parser.error(f"--input {name!r} was given more than once")
        cli_inputs[name] = path

    selected_entry = args.entry
    if args.case:
        try:
            selected_entry, case_cases_root = case_folder_record(args.case, driver_context=driver_context)
        except TutorialRecordError as exc:
            print(json.dumps({"status": "failed", "action": args.action, "error": str(exc)}, indent=2))
            return 1
        cases_root = case_cases_root
    elif repository is not None:
        cases_root = repository.tutorials
    else:
        # Unconditional: the chain always applies, so an unset --cases-root
        # means OMNIDRIVER_CASES_ROOT or the working directory, never a
        # location core invented.
        cases_root = resolve_cases_root(args.cases_root)
    overrides = {"cases_root": str(cases_root)}
    entry_label = getattr(selected_entry, "name", selected_entry)

    if args.action == "check":
        return _check(args, driver_context, repository, cases_root, cli_inputs)

    if args.action == "catalog":
        from .core.catalog_query import catalog_query

        try:
            result = catalog_query(
                selected_entry,
                cases_root=cases_root,
                document=args.document,
                key=args.key,
                driver_context=driver_context,
            )
        except (TutorialRecordError, KeyError) as exc:
            print(json.dumps({
                "status": "failed", "entry": entry_label, "action": "catalog", "error": str(exc),
            }, indent=2))
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.action == "describe":
        # A record refusal is JSON here, as in `plan --strict`.
        try:
            description = describe_entry(
                selected_entry,
                overrides=overrides,
                cli_study=cli_study,
                inputs=cli_inputs,
                driver_context=driver_context,
            )
        except TutorialRecordError as exc:
            print(json.dumps({
                "status": "failed",
                "entry": entry_label,
                "action": "describe",
                "error": str(exc),
            }, indent=2))
            return 1
        print(json.dumps(description, indent=2))
        return 0

    if args.action == "plan":
        if not args.strict:
            parser.error("action=plan currently requires --strict")
        try:
            report = strict_plan(
                selected_entry,
                overrides=overrides,
                environment_source=args.environment_source,
                allow_unresolved_configuration=args.allow_unresolved_configuration,
                scratch_root=args.scratch_dir,
                cli_study=cli_study,
                inputs=cli_inputs,
                driver_context=driver_context,
            )
        except TutorialRecordError as exc:
            print(json.dumps({
                "status": "failed",
                "entry": entry_label,
                "action": "plan",
                "error": str(exc),
            }, indent=2))
            return 1
        print(json.dumps(report.to_json(), indent=2))
        return 0 if report.status == "ok" else 1

    if args.action in {"step", "run"}:
        if not (args.strict or args.run_document):
            parser.error(f"action={args.action} requires --strict or --run-document")
        if args.action == "step" and not args.step:
            parser.error("action=step requires --step <id>")
        if args.run_document:
            return _run_document_dispatch(args, driver_context)
        context, failure_code = _context_from_entry(
            selected_entry=selected_entry,
            overrides=overrides,
            environment_source=args.environment_source,
            driver_context=driver_context,
            allow_unresolved_configuration=args.allow_unresolved_configuration,
            scratch_dir=args.scratch_dir,
            cli_study=cli_study,
            inputs=cli_inputs,
        )
        if context is None:
            return failure_code
        return _dispatch_context(args, context)

    if args.action == "sweep-plan":
        output_dir = _sweep_output_dir(args)
        if output_dir is None:
            return 1
        try:
            result = sweep_plan(
                args.spec,
                output_dir=output_dir,
                max_cases=args.max_cases,
                cli_study=cli_study,
                inputs=cli_inputs,
                driver_context=driver_context,
            )
        except (SweepValidationError, TutorialRecordError) as exc:
            return _sweep_refusal(args, exc)
        print(json.dumps(result, indent=2))
        # A spec that could not be read yields zero cases, so "no case
        # failed" would otherwise read as success.
        if result.get("spec_error"):
            return 1
        any_failed = any(case["status"] != "ok" for case in result["cases"])
        return 1 if any_failed else 0

    if args.action == "sweep-run":
        output_dir = _sweep_output_dir(args)
        if output_dir is None:
            return 1
        try:
            result = sweep_run(
                args.spec,
                output_dir=output_dir,
                max_cases=args.max_cases,
                case_timeout_s=args.case_timeout_s,
                fresh=args.fresh,
                cli_study=cli_study,
                inputs=cli_inputs,
                driver_context=driver_context,
            )
        except (SweepValidationError, TutorialRecordError) as exc:
            return _sweep_refusal(args, exc)
        print(json.dumps(result, indent=2))
        return 1 if result["failed_count"] > 0 else 0

    raise AssertionError(f"unreachable: unhandled action {args.action!r}")
