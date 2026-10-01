"""Load and adapt a RunDocument v3 for strict workflow execution.

``build_execution_inputs`` turns a document into the same executor inputs
``strict_plan`` produces, so the CLI run/step path is identical for both.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .configuration_source import resolve_configuration_source
from .models import DataArtifact, data_artifact_from_json
# _case_is_runnable is a private helper reused as-is rather than promoted to
# a public API.
from .registry import _case_is_runnable
from .run_model import RunDocument
from .workflow import normalize_workflow_dag, validate_workflow_commands, workflow_output_artifacts
from .workflow_state import (
    WorkflowRunState,
    initial_workflow_state,
    workflow_state_from_json,
)
from omnidriver.core.planning_types import SimulationAuditItem, StrictDiagnostic, diagnostic
from omnidriver.core.provider_identity import stack_identity_mismatch
from omnidriver.core.specs.validation import validate_run

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


#: The RunDocument's on-disk filename, named once here rather than restated
#: as a literal at each write/read site.
RUN_DOCUMENT_FILENAME = "run_document.json"


def _is_record_run_with_steps(run_doc: RunDocument) -> bool:
    """A tutorial-record run whose document carries the record's steps is
    runnable without asking the adapter's ``is_case_runnable_without_workflow``,
    since the record itself supplies the workflow DAG -- the wrong question
    for core to ask here. ``resolvedEntry.entryKind`` is stated by the
    planner, the same way ``configurationSource`` is stated rather than
    inferred."""
    resolved = run_doc.resolvedEntry if isinstance(run_doc.resolvedEntry, dict) else {}
    dag = run_doc.workflowDag if isinstance(run_doc.workflowDag, dict) else {}
    return resolved.get("entryKind") == "tutorial_record" and bool(dag.get("steps"))


@dataclass(frozen=True)
class RunDocumentExecutionInputs:
    """Everything the strict executor needs, derived from a RunDocument."""

    workflow_dag: dict[str, Any]
    workflow_state: WorkflowRunState
    case_root: Path
    output_dir: Path
    expected_artifacts: tuple[DataArtifact, ...]
    run_document: RunDocument
    #: Always empty: a RunDocument carries no plan-time simulation audit, so
    #: there is nothing to thread through to the dispatch-time coverage gate.
    simulation_audit: tuple[SimulationAuditItem, ...] = ()


def load_run_document(path: str | Path) -> RunDocument:
    """Read, schema-validate, and return a RunDocument from ``path``.

    The document is validated against ``schemas/run-document.json``, whose
    ``version`` is the constant ``"3"``: any other version is refused, never
    migrated. Raises ``ValueError`` on malformed input or schema-validation
    failure (a ``jsonschema.ValidationError`` is re-raised as ``ValueError``
    here, since it is not one itself), and ``json.JSONDecodeError`` on
    invalid JSON.
    """
    import jsonschema

    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("Run document must be a JSON object")
    try:
        return RunDocument.from_json(data)
    except jsonschema.exceptions.ValidationError as exc:
        raise ValueError(
            f"Run document at {path} failed schema validation: {exc.message}. "
            f"A field the schema does not accept is refused, never translated."
        ) from exc


#: Environment variable naming the only tree run outputs may be written to or
#: deleted from.
ALLOWED_RUNS_ROOT_ENV = "OMNIDRIVER_ALLOWED_RUNS_ROOT"


def _allowed_runs_root(env: dict[str, str] | None = None) -> Path | None:
    """Resolved allowed-runs root, or None when unset/empty."""
    source = env if env is not None else os.environ
    value = source.get(ALLOWED_RUNS_ROOT_ENV)
    if not value:
        return None
    return Path(value).resolve()


def _validate_config_against_plugin_schema(
    run_doc: RunDocument,
    driver_context: "DriverContext",
    diagnostics: list[StrictDiagnostic],
) -> None:
    """Append a ``plugin_config_schema_violation`` diagnostic per violation,
    mirroring ``run_document_adapter``'s emission-side check so planner and
    executor stay symmetric."""
    import jsonschema

    config_schema = driver_context.capabilities.run_document_configuration.schema()
    try:
        jsonschema.validate(run_doc.config, config_schema)
    except jsonschema.exceptions.ValidationError as exc:
        diagnostics.append(diagnostic(
            "error",
            "plugin_config_schema_violation",
            f"Plugin-declared config schema rejected the run document config: "
            f"{exc.message}",
            field=".".join(str(part) for part in exc.absolute_path) or "config",
        ))


def build_execution_inputs(
    run_doc: RunDocument,
    *,
    utility_produces: dict[str, tuple[str, ...]] | None = None,
    driver_context: "DriverContext",
    execution_env: Mapping[str, str] | None = None,
) -> tuple[RunDocumentExecutionInputs | None, tuple[StrictDiagnostic, ...]]:
    """Adapt ``run_doc`` into executor inputs.

    Returns ``(inputs, diagnostics)``. ``inputs`` is ``None`` whenever any
    error-level diagnostic is present (config invalid, no/invalid workflow
    DAG, disallowed command, no launch paths, unparseable artifact/state).
    ``diagnostics`` is always the full list, using the one canonical shape
    (``core.planning_types.StrictDiagnostic``: ``level, code, message,
    source, field``).
    """
    diagnostics: list[StrictDiagnostic] = []

    if run_doc.plugin is not None:
        planned = run_doc.plugin
        selected = driver_context.identity.to_json()
        # One source of truth for this comparison: see
        # `provider_identity.stack_identity_mismatch`'s docstring for what is
        # compared and why (also called from `cli.py` and
        # `quantities.comparison`).
        mismatched = stack_identity_mismatch(planned, selected)
        if mismatched:
            diagnostics.append(diagnostic(
                "error",
                "plugin_identity_mismatch",
                "RunDocument plugin does not match the supplied driver context: "
                + ", ".join(mismatched),
                field="plugin",
            ))

    # 1) Config validity against the selected plugin's live dictionary
    # catalog and semantic validators, plus the plugin-declared config
    # schema (1b) -- but only when this document's own `config` is the
    # configuration to check. `run_doc.configurationSource` states that
    # explicitly, and `resolve_configuration_source` is the SAME function
    # `run_document_adapter._run_document_from_case` calls on the emission
    # path, so a config the planner would refuse to emit is a config the
    # executor refuses to ingest -- one rule, not two that can drift.
    #
    # An ingested, agent-authored document is untrusted: declaring "case" is
    # refused outright when `config` is not actually empty -- an attacker
    # cannot use "case" to smuggle unvalidated document config past this
    # gate, and the plugin-identity check just above still applies
    # regardless of `configurationSource`.
    source_decision = resolve_configuration_source(
        getattr(run_doc, "configurationSource", None), run_doc.config,
    )
    diagnostics.extend(source_decision.diagnostics)
    if source_decision.validate_document_config:
        # `validate_run` already returns the canonical `StrictDiagnostic`
        # shape (with `source` carrying the phase), so these pass through
        # unchanged.
        diagnostics.extend(validate_run(run_doc, driver_context=driver_context))
        _validate_config_against_plugin_schema(run_doc, driver_context, diagnostics)

    # 2) Expected artifacts: reconstruct, reporting any malformed entry.
    expected_artifacts: list[DataArtifact] = []
    raw_artifacts = run_doc.expectedArtifacts
    if not isinstance(raw_artifacts, (list, tuple)):
        diagnostics.append(diagnostic(
            "error", "invalid_expected_artifacts",
            f"expectedArtifacts must be a list, got {type(raw_artifacts).__name__}.",
            field="expectedArtifacts",
        ))
        raw_artifacts = []
    for raw in raw_artifacts:
        try:
            expected_artifacts.append(data_artifact_from_json(raw))
        except Exception as exc:  # malformed shape / unknown placeholder
            diagnostics.append(
                diagnostic("error", "invalid_expected_artifact", str(exc), field="expectedArtifacts")
            )

    # 3) Re-normalize the supplied DAG so a hand-authored workflow gets the
    #    same shape guarantees and diagnostics as a strict-planned one.
    dag, wf_diagnostics = normalize_workflow_dag(
        run_doc.workflowDag,
        expected_artifacts=workflow_output_artifacts(expected_artifacts),
        utility_produces=utility_produces,
        driver_context=driver_context,
    )
    for d in wf_diagnostics:
        diagnostics.append(diagnostic(d.level, d.code, d.message, field=d.field))

    # 4) Command allowlist — same gate as the --entry path.
    for d in validate_workflow_commands(dag, driver_context=driver_context):
        diagnostics.append(diagnostic(d.level, d.code, d.message, field=d.field))

    # 5) Launch paths are mandatory for execution.
    raw_launch = run_doc.launch
    if raw_launch is None:
        launch: dict[str, Any] = {}
    elif isinstance(raw_launch, dict):
        launch = raw_launch
    else:
        launch = {}
        diagnostics.append(diagnostic(
            "error", "invalid_launch",
            f"Run document launch must be a JSON object, got {type(raw_launch).__name__}.",
            field="launch",
        ))
    case_root_raw = launch.get("caseRoot")
    output_dir_raw = launch.get("outputDir")
    if not case_root_raw:
        diagnostics.append(diagnostic(
            "error", "missing_case_root",
            "Run document launch.caseRoot is required for execution.",
            field="launch.caseRoot",
        ))
    if not output_dir_raw:
        diagnostics.append(diagnostic(
            "error", "missing_output_dir",
            "Run document launch.outputDir is required for execution.",
            field="launch.outputDir",
        ))

    # 5b) Validate + canonicalize launch paths against the selected adapter's
    # case contract. caseRoot is the solver/environment output base and must
    # be runnable according to that adapter. Resolve (follow symlinks) so all
    # downstream checks and the artifact gate use one canonical absolute path.
    resolved_case_root: Path | None = None
    if case_root_raw:
        resolved_case_root = Path(case_root_raw).resolve()
        if not resolved_case_root.exists():
            diagnostics.append(diagnostic(
                "error", "case_root_missing",
                f"Run document launch.caseRoot does not exist: {case_root_raw}.",
                field="launch.caseRoot",
            ))
            resolved_case_root = None
        elif not resolved_case_root.is_dir():
            diagnostics.append(diagnostic(
                "error", "case_root_not_a_directory",
                f"Run document launch.caseRoot is not a directory: {case_root_raw}.",
                field="launch.caseRoot",
            ))
            resolved_case_root = None
        elif not _is_record_run_with_steps(run_doc) and not _case_is_runnable(
            resolved_case_root, driver_context=driver_context,
        ):
            diagnostics.append(diagnostic(
                "error", "case_root_not_a_runnable_case",
                f"Run document launch.caseRoot is not runnable according to the "
                f"selected adapter: {case_root_raw}.",
                field="launch.caseRoot",
            ))
            resolved_case_root = None

    # outputDir is the driver-bookkeeping base. Resolve the same way the driver
    # builds it (resolve_spec_paths): absolute as-is, relative under caseRoot.
    resolved_output_dir: Path | None = None
    if output_dir_raw:
        candidate = Path(output_dir_raw)
        if candidate.is_absolute():
            resolved_output_dir = candidate.resolve()
        elif resolved_case_root is not None:
            resolved_output_dir = (resolved_case_root / candidate).resolve()
        else:
            # resolved_case_root is None here (caseRoot missing/invalid), which
            # already forces `blocked = True` below regardless of outputDir.
            # This CWD-relative resolution is never actually used for
            # execution — computed only so every branch yields a value.
            resolved_output_dir = candidate.resolve()

    # Opt-in hard boundary: when the allowed-runs-root variable is set, both
    # resolved paths must sit under it. Runs on resolved paths, so a symlink or
    # an absolute output_dir cannot escape. Unset -> skipped (no behavior change).
    allowed_root = _allowed_runs_root()
    if allowed_root is not None:
        if resolved_case_root is not None and not resolved_case_root.is_relative_to(allowed_root):
            diagnostics.append(diagnostic(
                "error", "case_root_outside_allowed_root",
                f"launch.caseRoot resolves outside {ALLOWED_RUNS_ROOT_ENV} "
                f"({allowed_root}): {resolved_case_root}.",
                field="launch.caseRoot",
            ))
        if resolved_output_dir is not None and not resolved_output_dir.is_relative_to(allowed_root):
            diagnostics.append(diagnostic(
                "error", "output_dir_outside_allowed_root",
                f"launch.outputDir resolves outside {ALLOWED_RUNS_ROOT_ENV} "
                f"({allowed_root}): {resolved_output_dir}.",
                field="launch.outputDir",
            ))

    # 6) Workflow state: prefer the document's snapshot, else derive from DAG.
    workflow_state: WorkflowRunState | None
    if run_doc.workflowState is not None:
        try:
            workflow_state = workflow_state_from_json(run_doc.workflowState)
        except Exception as exc:
            workflow_state = None
            diagnostics.append(
                diagnostic("error", "invalid_workflow_state", str(exc), field="workflowState")
            )
    else:
        # Computed regardless of earlier errors so all diagnostics are gathered
        # before the single blocked check below.
        workflow_state = initial_workflow_state(dag) if dag is not None else None

    # An embedded non-initial state is resumable evidence just like the
    # adjacent workflow_state.json checkpoint.  Without this gate a completed
    # state copied into a RunDocument could suppress execution after its case
    # inputs changed, because only on-disk checkpoints reached the CLI resume
    # validation path.  validate_resume deliberately permits a fresh,
    # zero-attempt pending state without a snapshot.
    if (
        run_doc.workflowState is not None
        and workflow_state is not None
        and dag is not None
        and resolved_case_root is not None
    ):
        from .resume import validate_resume

        try:
            validate_resume(
                workflow_state,
                dag,
                case_root=resolved_case_root,
                driver_context=driver_context,
                env=execution_env,
                expected_artifacts=tuple(expected_artifacts),
            )
        except Exception as exc:
            diagnostics.append(diagnostic(
                "error",
                "workflow_state_resume_rejected",
                f"Run document workflowState cannot be resumed: {exc}",
                field="workflowState",
            ))

    blocked = (
        any(d.level == "error" for d in diagnostics)
        or dag is None
        or workflow_state is None
        or resolved_case_root is None
        or resolved_output_dir is None
    )
    if blocked:
        return None, tuple(diagnostics)

    inputs = RunDocumentExecutionInputs(
        workflow_dag=dag,
        workflow_state=workflow_state,
        case_root=resolved_case_root,
        output_dir=resolved_output_dir,
        expected_artifacts=tuple(expected_artifacts),
        run_document=run_doc,
    )
    return inputs, tuple(diagnostics)
