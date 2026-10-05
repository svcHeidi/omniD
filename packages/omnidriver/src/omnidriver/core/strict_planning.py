from __future__ import annotations

import json
import os
import shlex
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


from .runtime.artifacts import predict_data_artifacts
from .runtime.execution_context import resolve_execution_context
from .runtime.models import DataArtifact
from .runtime.record_execution import commit_and_build_record_spec
from .runtime.repository_staging import copy_repository_scripts, staged_case_path
from .runtime.run_command import omnidriver_run_command
from .runtime.run_document_adapter import build_run_document
from .runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from .runtime.run_model import RunDocument
from .runtime.strict_audit import _build_simulation_audit
from .runtime.workflow import (
    WorkflowDiagnostic,
    normalize_workflow_dag,
    validate_workflow_commands,
    workflow_output_artifacts,
)
from .runtime.workflow_state import WorkflowRunState, initial_workflow_state
from omnidriver.core.planning_types import (
    StrictDiagnostic,
    SimulationAuditItem,
    artifact_to_json as _artifact_to_json,
    diagnostic as _diagnostic,
    has_error,
)
from .specs.paths import resolve_scratch_root
from .tutorial_records import TutorialRecord, TutorialRecordError, lookup_record


@dataclass(frozen=True)
class StrictPlanReport:
    status: str
    entry: str
    resolved_entry: dict[str, Any]
    readiness_score: dict[str, Any] = field(default_factory=dict)
    simulation_audit: tuple[SimulationAuditItem, ...] = ()
    workflow_diagnostics: tuple[StrictDiagnostic, ...] = ()
    artifact_diagnostics: tuple[StrictDiagnostic, ...] = ()
    environment_diagnostics: tuple[StrictDiagnostic, ...] = ()
    plugin_diagnostics: tuple[StrictDiagnostic, ...] = ()
    launch: dict[str, Any] = field(default_factory=dict)
    workflow_dag: dict[str, Any] | None = None
    workflow_state: WorkflowRunState | None = None
    expected_artifacts: tuple[DataArtifact, ...] = ()
    run_document: RunDocument | None = None
    capability_manifest: dict[str, Any] = field(default_factory=dict)
    configuration_evidence: tuple[dict[str, Any], ...] = ()
    configuration_evidence_policy: str = "strict"
    configuration_diagnostics: tuple[StrictDiagnostic, ...] = ()
    plugin: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "entry": self.entry,
            "resolved_entry": self.resolved_entry,
            "readiness_score": self.readiness_score,
            "simulation_audit": [asdict(item) for item in self.simulation_audit],
            "workflow_diagnostics": [asdict(d) for d in self.workflow_diagnostics],
            "artifact_diagnostics": [asdict(d) for d in self.artifact_diagnostics],
            "environment_diagnostics": [asdict(d) for d in self.environment_diagnostics],
            "plugin_diagnostics": [asdict(d) for d in self.plugin_diagnostics],
            "launch": self.launch,
            "workflow_dag": self.workflow_dag,
            "workflow_state": self.workflow_state.to_json() if self.workflow_state else None,
            "expected_artifacts": [_artifact_to_json(a) for a in self.expected_artifacts],
            "run_document": self.run_document.to_json() if self.run_document else None,
            "capability_manifest": self.capability_manifest,
            "configuration_evidence": list(self.configuration_evidence),
            "configuration_evidence_policy": self.configuration_evidence_policy,
            "configuration_diagnostics": [
                asdict(diagnostic) for diagnostic in self.configuration_diagnostics
            ],
            "plugin": self.plugin,
        }


def _jsonable(value: Any) -> Any:
    """Convert plugin capability metadata into a report-safe value."""
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    return value


def _workflow_diagnostic_to_strict(diagnostic: WorkflowDiagnostic) -> StrictDiagnostic:
    return _diagnostic(
        diagnostic.level,
        diagnostic.code,
        diagnostic.message,
        source="workflow_dag",
        field=diagnostic.field,
    )


def _utility_produces_by_command(
    driver_context: "DriverContext",
) -> dict[str, tuple[str, ...]]:
    """The active plugin's utilities, keyed to the artifacts they declare."""

    from omnidriver.core.capability_manifest import utility_produces

    return utility_produces(
        driver_context.stack.call("get_utility_manifests")
    )


def _workflow_command_diagnostics(
    workflow_dag: dict[str, Any] | None,
    driver_context: "DriverContext",
) -> tuple[StrictDiagnostic, ...]:
    diagnostics: list[StrictDiagnostic] = []

    for diagnostic in validate_workflow_commands(
        workflow_dag, driver_context=driver_context,
    ):
        diagnostics.append(_diagnostic(
            diagnostic.level,
            diagnostic.code,
            diagnostic.message,
            field=diagnostic.field,
        ))

    return tuple(diagnostics)


_EXPLORABLE_CONFIGURATION_STATUSES = frozenset({
    "unresolved", "execution_required", "runtime_unavailable",
})


def _configuration_evidence_diagnostics(
    evidence: tuple[dict[str, Any], ...], *, allow_unresolved_configuration: bool,
) -> tuple[StrictDiagnostic, ...]:
    """Unresolved states are errors, or warnings under ``allow_unresolved_configuration``; an unknown status is never made launchable."""
    diagnostics: list[StrictDiagnostic] = []
    for record in evidence:
        dictionary = str(record.get("dictionary", "<unknown>"))
        status = record.get("status")
        if status == "inspected":
            continue
        message = str(record.get("message") or "no inspection detail was supplied")
        if status in _EXPLORABLE_CONFIGURATION_STATUSES:
            level = "warning" if allow_unresolved_configuration else "error"
            suffix = (
                "; allowed only because this plan explicitly requests an exploratory run"
                if allow_unresolved_configuration else
                "; use --allow-unresolved-configuration only for an explicitly exploratory run"
            )
            code = f"configuration_{status}"
        else:
            level = "error"
            suffix = "; the plugin returned an unknown configuration evidence status"
            code = "configuration_unknown_status"
        diagnostics.append(_diagnostic(
            level,
            code,
            f"{dictionary}: {message}{suffix}",
            source="configuration_evidence",
            field=dictionary,
        ))
    return tuple(diagnostics)


def _run_launch_description(context, *, driver_context: "DriverContext") -> dict[str, Any]:
    """The ``run --run-document`` invocation; paths are absolute because a relative ``outputDir`` is read as under ``caseRoot``."""
    run_document_path = str(Path(context.output_dir).absolute() / RUN_DOCUMENT_FILENAME)
    command = omnidriver_run_command(driver_context, "--run-document", run_document_path)
    return {
        "action": "run",
        "command": command,
        "command_display": shlex.join(command),
        "workflow_state_path": str(Path(context.workflow_state_path).absolute()),
        "case_root": str(Path(context.case_root).absolute()),
        "setup_root": str(Path(context.setup_root).absolute()),
        "output_dir": str(Path(context.output_dir).absolute()),
    }


def strict_plan(
    entry: "str | TutorialRecord",
    *,
    overrides: dict[str, Any] | None = None,
    environment_source: str | None = None,
    allow_unresolved_configuration: bool = False,
    scratch_root: str | Path | None = None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> StrictPlanReport:
    """Plan (and commit) one tutorial-record case: ``plan --strict``,
    and what ``step``/``run`` start from.

    ``entry`` is a record name in the composed stack's catalogue, or a record
    built for a case folder (``tutorial_records.case_folder_record``).
    ``overrides`` carries ``cases_root``, which names where the record's
    native case lives -- there is no ambient cases root to discover -- and
    otherwise this single case's own study values (``base``, no ``sweep``
    values: one resolved case). ``cli_study`` holds the study values the CLI
    itself supplies (``--parallel``), kept as the study's own ``"cli"``
    source beside ``overrides``' ``"base"``, so a CLI value that disagrees
    with the study's is refused by name rather than merged. ``inputs``
    (``--input NAME=PATH``, repeatable) supplies the record's declared
    inputs.

    The case is staged at ``<scratch_root>/records/<name>``; a case folder
    (``--case``) inside the supplied repository is staged at its
    repository-relative depth under that, beside a copy of the repository's
    ``scripts`` folder, so a native ``Allrun`` that reaches its repository's
    scripts from ``$case/../..`` runs. The scratch
    root is supplied (``scratch_root``, else ``OMNIDRIVER_SCRATCH_DIR``) or
    refused by name, and a root inside ``cases_root`` is refused. The plan
    commits the case as a side effect and persists its ``RunDocument`` to
    ``<output_dir>/run_document.json``, the path ``launch`` advertises as
    ``run --run-document <path>``, so that command is immediately runnable.
    """
    record = lookup_record(entry, driver_context=driver_context)
    incoming_overrides = dict(overrides or {})
    cases_root_value = incoming_overrides.get("cases_root")
    if cases_root_value is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot be planned: 'cases_root' must "
            "name where its native case lives (there is no ambient cases "
            "root to discover); supply --cases-root or OMNIDRIVER_CASES_ROOT"
        )
    cases_root = Path(cases_root_value)
    study_by_source = {
        "base": {key: value for key, value in incoming_overrides.items() if key != "cases_root"},
        "sweep": {},
        "cli": dict(cli_study or {}),
    }
    resolved_scratch_root = resolve_scratch_root(scratch_root, cases_root=cases_root)
    staging_root = resolved_scratch_root / "records" / record.name
    staged_case_root = staging_root
    if isinstance(entry, TutorialRecord):
        native_case = cases_root / record.native_case_relpath
        staged_case_root = staged_case_path(
            native_case, driver_context.repository, staging_root=staging_root, flat=staging_root,
        )
        copy_repository_scripts(driver_context.repository, native_case, staging_root=staging_root)
    try:
        _commit_result, spec = commit_and_build_record_spec(
            record,
            case_id=record.name,
            cases_root=cases_root,
            staged_case_root=staged_case_root,
            study_by_source=study_by_source,
            driver_context=driver_context,
            inputs=inputs,
        )
    except PermissionError as exc:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot be staged under {staged_case_root}: {exc}. "
            "Supply a writable scratch root outside the cases root with "
            "--scratch-dir (or OMNIDRIVER_SCRATCH_DIR)"
        ) from exc
    report = _strict_plan_for_spec(
        record.name,
        spec,
        environment_source=environment_source,
        allow_unresolved_configuration=allow_unresolved_configuration,
        driver_context=driver_context,
        scratch_root=resolved_scratch_root,
    )
    run_document_path = Path(report.launch["output_dir"]) / RUN_DOCUMENT_FILENAME
    run_document_path.parent.mkdir(parents=True, exist_ok=True)
    run_document_path.write_text(json.dumps(report.run_document.to_json(), indent=2))
    return report


def _strict_plan_for_spec(
    entry: str,
    spec: Any,
    *,
    environment_source: str | None = None,
    allow_unresolved_configuration: bool = False,
    driver_context: "DriverContext",
    scratch_root: Path | None = None,
) -> StrictPlanReport:
    """Diagnostics and run-document assembly for one committed case, shared by ``strict_plan`` and the sweep runner."""
    execution_context = resolve_execution_context(spec)
    launch = _run_launch_description(execution_context, driver_context=driver_context)
    artifacts = tuple(
        predict_data_artifacts(
            Path(spec.case_root), spec, driver_context=driver_context,
        )
    )
    workflow_dag, workflow_diagnostics_raw = normalize_workflow_dag(
        spec.metadata.get("workflow_dag") if spec.metadata else None,
        expected_artifacts=workflow_output_artifacts(artifacts),
        utility_produces=_utility_produces_by_command(driver_context),
        driver_context=driver_context,
    )
    workflow_diagnostics = tuple(
        _workflow_diagnostic_to_strict(diagnostic)
        for diagnostic in workflow_diagnostics_raw
    )
    workflow_state = initial_workflow_state(workflow_dag)
    run_document = build_run_document(
        entry=entry,
        spec=spec,
        launch=launch,
        workflow_dag=workflow_dag,
        workflow_state=workflow_state,
        expected_artifacts=artifacts,
        driver_context=driver_context,
    )
    artifact_diagnostics = _workflow_command_diagnostics(workflow_dag, driver_context)
    env_diagnostics = driver_context.stack.call(
        "get_environment_diagnostics",
        workflow_dag,
        environment_source=environment_source,
        driver_context=driver_context,
    )
    plugin_diagnostics = driver_context.stack.call(
        "get_plan_diagnostics",
        Path(spec.case_root),
        workflow_dag=workflow_dag,
        env=os.environ,
        scratch_root=scratch_root,
        driver_context=driver_context,
    )
    configuration_evidence = driver_context.stack.call(
        "inspect_effective_configuration", case_root=Path(spec.case_root), execution_env=dict(os.environ),
    )
    configuration_diagnostics = _configuration_evidence_diagnostics(
        configuration_evidence,
        allow_unresolved_configuration=allow_unresolved_configuration,
    )
    configuration_evidence_policy = (
        "exploratory" if allow_unresolved_configuration else "strict"
    )
    simulation_audit, readiness_score = _build_simulation_audit(
        workflow_dag=workflow_dag,
        artifacts=artifacts,
        workflow_diagnostics=workflow_diagnostics,
        artifact_diagnostics=artifact_diagnostics,
        environment_diagnostics=env_diagnostics,
    )
    plan_diagnostics = (
        workflow_diagnostics
        + artifact_diagnostics
        + plugin_diagnostics
        + configuration_diagnostics
    )
    from .capability_manifest import capability_manifest as stack_manifest

    raw_capability_manifest = stack_manifest(driver_context)
    raw_capability_manifest["plugin_identity"] = driver_context.identity.to_json()
    capability_manifest = _jsonable(raw_capability_manifest)
    all_diagnostics = plan_diagnostics + env_diagnostics
    failed = has_error(plan_diagnostics)
    blocked = has_error(env_diagnostics)
    run_document.status = "failed" if failed else "planned"
    run_document.validation = {
        "status": "failed" if failed else "ok",
        "diagnostics": [asdict(diagnostic) for diagnostic in all_diagnostics],
    }
    run_document.intent["configuration_evidence_policy"] = configuration_evidence_policy
    unresolved_dictionaries = [
        str(record.get("dictionary", "<unknown>"))
        for record in configuration_evidence
        if record.get("status") != "inspected"
    ]
    if unresolved_dictionaries:
        run_document.intent["unresolved_configuration_dictionaries"] = unresolved_dictionaries
    return StrictPlanReport(
        status="failed" if failed else "blocked" if blocked else "ok",
        entry=entry,
        resolved_entry={
            "entry_name": spec.metadata.get("entry_name", entry),
            "entry_path": spec.metadata.get("entry_path"),
        },
        readiness_score=readiness_score,
        simulation_audit=simulation_audit,
        workflow_diagnostics=workflow_diagnostics,
        artifact_diagnostics=artifact_diagnostics,
        environment_diagnostics=env_diagnostics,
        plugin_diagnostics=plugin_diagnostics,
        launch=launch,
        workflow_dag=workflow_dag,
        workflow_state=workflow_state,
        expected_artifacts=artifacts,
        run_document=run_document,
        capability_manifest=capability_manifest,
        configuration_evidence=configuration_evidence,
        configuration_evidence_policy=configuration_evidence_policy,
        configuration_diagnostics=configuration_diagnostics,
        plugin=driver_context.identity.to_json(),
    )
