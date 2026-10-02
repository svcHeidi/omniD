from __future__ import annotations

import fnmatch
import json
import os
import shlex
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


import shutil

from .runtime.artifacts import predict_data_artifacts
from .runtime.execution_context import resolve_execution_context
from .runtime.models import DataArtifact
from .runtime.record_execution import commit_and_build_record_spec
from .runtime.registry import classify_entry, load_entry_spec
from .runtime.run_command import omnidriver_run_command
from .runtime.run_document_adapter import _run_document_from_case
from .runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from .runtime.run_model import RunDocument
from .runtime.strict_audit import SKIP_GEOMETRY_DIAGNOSTICS_ENV, _build_simulation_audit
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
)
from .contracts.catalogue_paths import catalogued_paths as _catalogued_paths
from .specs.paths import resolve_scratch_root
from .tutorial_records import TutorialRecordError


@dataclass(frozen=True)
class StrictPlanReport:
    status: str
    entry: str
    resolved_entry: dict[str, Any]
    readiness_score: dict[str, Any] = field(default_factory=dict)
    simulation_audit: tuple[SimulationAuditItem, ...] = ()
    validation_diagnostics: tuple[StrictDiagnostic, ...] = ()
    workflow_diagnostics: tuple[StrictDiagnostic, ...] = ()
    catalog_coverage_errors: tuple[StrictDiagnostic, ...] = ()
    artifact_diagnostics: tuple[StrictDiagnostic, ...] = ()
    environment_diagnostics: tuple[StrictDiagnostic, ...] = ()
    mesh_geometry_diagnostics: tuple[StrictDiagnostic, ...] = ()
    launch: dict[str, Any] = field(default_factory=dict)
    workflow_dag: dict[str, Any] | None = None
    workflow_state: WorkflowRunState | None = None
    expected_artifacts: tuple[DataArtifact, ...] = ()
    run_document: RunDocument | None = None
    capability_manifest: dict[str, Any] = field(default_factory=dict)
    function_object_diagnostics: tuple[StrictDiagnostic, ...] = ()
    case_dict_key_diagnostics: tuple[StrictDiagnostic, ...] = ()
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
            "validation_diagnostics": [asdict(d) for d in self.validation_diagnostics],
            "workflow_diagnostics": [asdict(d) for d in self.workflow_diagnostics],
            "catalog_coverage_errors": [asdict(d) for d in self.catalog_coverage_errors],
            "artifact_diagnostics": [asdict(d) for d in self.artifact_diagnostics],
            "environment_diagnostics": [asdict(d) for d in self.environment_diagnostics],
            "mesh_geometry_diagnostics": [
                asdict(d) for d in self.mesh_geometry_diagnostics
            ],
            "launch": self.launch,
            "workflow_dag": self.workflow_dag,
            "workflow_state": self.workflow_state.to_json() if self.workflow_state else None,
            "expected_artifacts": [_artifact_to_json(a) for a in self.expected_artifacts],
            "run_document": self.run_document.to_json() if self.run_document else None,
            "capability_manifest": self.capability_manifest,
            "function_object_diagnostics": [
                asdict(d) for d in self.function_object_diagnostics
            ],
            "case_dict_key_diagnostics": [
                asdict(d) for d in self.case_dict_key_diagnostics
            ],
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
        driver_context.capabilities.command_authorization.utility_manifests()
    )


def _artifact_diagnostics(
    spec,
    artifacts: tuple[DataArtifact, ...],
    workflow_dag: dict[str, Any] | None,
    driver_context: "DriverContext",
) -> tuple[StrictDiagnostic, ...]:
    from .runtime.workflow import validate_workflow_commands

    diagnostics: list[StrictDiagnostic] = []
    case_root = Path(spec.case_root)

    if not artifacts:
        diagnostics.append(_diagnostic(
            "error",
            "empty_artifact_prediction",
            "Strict planning could not predict any artifacts for this entry.",
            source=str(case_root),
        ))

    # Defer domain-specific validation to the selected capability while
    # preserving the public plugin call and diagnostic order.
    from .plugin_capabilities import ConfigurationValidationRequest

    diagnostics.extend(
        driver_context.capabilities.configuration_validator.validate(
            ConfigurationValidationRequest(spec),
        )
    )

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


def _owned_dict_relpaths(spec, driver_context: "DriverContext") -> tuple[str, ...]:
    """Case dictionaries the active plugin's catalogue actually addresses.

    Only dictionaries the catalogue covers may be swept -- warning about keys
    in an uncatalogued file would be pure noise. The spec's own
    ``dict_file_relpaths`` metadata is authoritative when present; older
    adapters may instead expose ``*_relpath`` metadata, read via a
    suffix-based compatibility fallback. A bare case folder has no metadata,
    so the plugin's document names are matched against the adapter's declared
    case-file rules -- core never supplies a directory layout or document
    vocabulary itself.
    """
    metadata = getattr(spec, "metadata", None) or {}
    relpaths: list[str] = []
    configured = metadata.get("dict_file_relpaths")
    if isinstance(configured, dict):
        values = configured.values()
    else:
        values = (
            value for key, value in metadata.items()
            if str(key).endswith("_relpath")
        )
    for value in values:
        if value and str(value) not in relpaths:
            relpaths.append(str(value))
    if relpaths:
        return tuple(relpaths)

    case_root = Path(spec.case_root)
    documents = driver_context.capabilities.dictionaries.documents()
    rules = driver_context.capabilities.case_files.all_rules()
    for document in documents:
        for rule in rules:
            pattern = str(rule.path)
            if Path(pattern).is_absolute():
                continue
            basename = PurePosixPath(pattern).name
            if not (
                fnmatch.fnmatch(basename, str(document))
                or fnmatch.fnmatch(str(document), basename)
            ):
                continue
            candidates = (
                case_root.glob(pattern)
                if any(char in pattern for char in "*?[")
                else (case_root / pattern,)
            )
            for candidate_path in candidates:
                if candidate_path.is_file():
                    candidate = candidate_path.relative_to(case_root).as_posix()
                    if candidate not in relpaths:
                        relpaths.append(candidate)
    return tuple(relpaths)


def _catalog_diagnostics(
    driver_context: "DriverContext", *, scan_cache_root: Path | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """The resolved cxx_mapping provider's catalogue compared with its C++:
    an error per contradiction, a note per uncatalogued read."""

    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    if mapping is None:
        return ()
    # `source=` names whichever provider actually answered `cxx_mapping`, per
    # `resolutions()` -- `StackIdentity` has no singular id to fall back on.
    cxx_mapping_source = driver_context.identity.resolutions.get(
        "cxx_mapping", "cxx_mapping",
    )
    source_root = mapping.source_root(os.environ)
    if source_root is None:
        # Supplied, never discovered: an unsupplied root is reported as info,
        # not a warning, so a plan that needs no C++ scanning isn't flagged.
        return (_diagnostic(
            "info",
            "plugin_cxx_source_not_supplied",
            f"C++ source not scanned: source root not supplied (set "
            f"{mapping.source_root_variable}; the source is "
            f"${mapping.source_root_variable}/{mapping.source_root_relative})",
            source=cxx_mapping_source,
        ),)
    if not source_root.is_dir():
        return (_diagnostic(
            "error",
            "plugin_cxx_source_unavailable",
            f"{mapping.source_root_variable} is supplied, but its C++ source "
            f"{source_root} is not a directory",
            source=cxx_mapping_source,
        ),)
    report = driver_context.capabilities.dict_key_scanner.scan(
        source_root,
        allowlist_path=mapping.allowlist_path,
        entries=driver_context.capabilities.dictionaries.entries(),
        cache_root=scan_cache_root,
    ).to_json()
    source = f"{cxx_mapping_source}:{source_root}"
    contradictions = tuple(
        _diagnostic("error", "plugin_catalog_contradiction", item, source=source)
        for item in report.get("contradictions", ())
    )
    notes = tuple(
        _diagnostic(
            "info", "plugin_catalog_uncatalogued",
            f"the C++ reads {json.dumps(item, sort_keys=True)}, which the catalogue lacks "
            "(omnidriver catalog --uncatalogued lists every one)",
            source=source,
        )
        for item in report.get("uncatalogued", ())
    )
    return contradictions + notes


def _mesh_geometry_exempt(spec, driver_context: "DriverContext") -> bool:
    """Whether the SI mesh-scale gate is not meaningful for this case.

    Two answers only: the plugin's own ``is_nondimensional_case``, read
    from the case's files, or a generic case, whose conventions core
    does not know. There is no exemption by entry name or workflow family.
    """
    return (
        driver_context.capabilities.mesh_diagnostic_policy.is_nondimensional(spec)
        or bool(spec.metadata.get("generic_case"))
    )


def _mesh_geometry_diagnostics(
    case_root: str | Path,
    *,
    exempt: bool = False,
    driver_context: "DriverContext",
) -> tuple[StrictDiagnostic, ...]:
    """Adapt mesh-scale detection into StrictDiagnostics for the report.

    The active plugin's base geometry check classifies its mesh regions'
    scale; the plugin may add checks for point sets that are not mesh
    regions (cardiacFoam's ``constant/purkinjeGraph*``). Both report under
    the same ``mesh_geometry`` source, and both are skipped by the same
    exemption.
    """
    if exempt or SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ:
        return ()
    detected = list(
        driver_context.capabilities.mesh_diagnostic_policy.base_geometry_diagnostics(
            Path(case_root),
        )
    )
    detected.extend(
        driver_context.capabilities.mesh_diagnostic_policy.extra_geometry_diagnostics(
            Path(case_root),
        )
    )
    return tuple(
        _diagnostic(
            d.level,
            d.code,
            d.message,
            source="mesh_geometry",
            field=d.region,
        )
        for d in detected
    )


def _has_error(diagnostics: tuple[StrictDiagnostic, ...]) -> bool:
    return any(diagnostic.level == "error" for diagnostic in diagnostics)


_EXPLORABLE_CONFIGURATION_STATUSES = frozenset({
    "unresolved", "execution_required", "runtime_unavailable",
})


def _configuration_evidence_diagnostics(
    evidence: tuple[dict[str, Any], ...], *, allow_unresolved_configuration: bool,
) -> tuple[StrictDiagnostic, ...]:
    """Turn declared configuration-closure limits into an explicit policy.

    ``inspected`` is the normal, launchable state.  The three declared
    unresolved states are errors for a normal plan.  An operator may opt into
    an exploratory run with ``allow_unresolved_configuration``; those exact
    known states then remain visible as warnings and are recorded in the run
    intent.  Unknown status strings are never made launchable by the flag:
    that would turn a future plugin contract into an implicit bypass.
    """
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


def _run_launch_description(
    entry: str,
    context,
    *,
    driver_context: "DriverContext",
    entry_kind: str | None,
    config_path: str | Path | None,
    allow_unresolved_configuration: bool = False,
    is_tutorial_record: bool = False,
) -> dict[str, Any]:
    """Describe the `run --strict --entry` invocation for this plan.

    The four paths are written absolute. They become the run document's
    ``launch`` block, read by ``run_document_exec.build_execution_inputs``
    under its own rule (a relative ``outputDir`` is under ``caseRoot``, a
    relative ``caseRoot`` is under the reader's working directory) --
    writing them as supplied, already joined under a possibly relative
    ``cases_root``, would nest ``outputDir`` twice.

    A tutorial record has no ``load_entry_spec`` resolution at all (it is
    inert data, not a factory -- ``registry._materialize_resolved_entry``
    refuses it by name), so its launch command cannot re-resolve the way a
    factory entry's does. Its case was already committed once by the caller
    that built this plan, so the launch command instead points at the run
    document THIS PLAN becomes, once its caller persists it at
    ``output_dir/run_document.json``. ``entry_kind``/``config_path``/
    ``allow_unresolved_configuration`` name a ``load_entry_spec``
    re-resolution a record never performs, so none apply to this branch.
    """
    if is_tutorial_record:
        run_document_path = str(
            Path(context.output_dir).absolute() / RUN_DOCUMENT_FILENAME
        )
        command = omnidriver_run_command(driver_context, "--run-document", run_document_path)
    else:
        command = omnidriver_run_command(driver_context, "--strict", "--entry", entry)
        if entry_kind is not None:
            command.extend(["--entry-kind", entry_kind])
        if config_path is not None:
            command.extend(["--config", str(config_path)])
        if allow_unresolved_configuration:
            command.append("--allow-unresolved-configuration")
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
    entry: str,
    *,
    entry_kind: str | None = None,
    overrides: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    environment_source: str | None = None,
    allow_unresolved_configuration: bool = False,
    scratch_root: str | Path | None = None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> StrictPlanReport:
    """Build a non-mutating strict simulation plan report.

    ``inputs`` (``--input NAME=PATH``, repeatable) supplies a tutorial
    record's declared inputs; refused by name for any other entry (the same
    posture ``cli_study`` has -- :func:`refuse_cli_study_for_non_record`).

    ``cli_study`` holds the study values the CLI itself supplies (e.g.
    ``--parallel``), kept as a record study's own ``"cli"`` source beside
    ``overrides``' ``"base"``, so a CLI value that disagrees with the
    study's is refused by name rather than merged. Only a tutorial record
    takes study values; any other entry given one is refused by name.

    ``scratch_root`` is where a tutorial record's case is staged
    (``<scratch_root>/records/<name>``), resolved via
    ``specs.paths.resolve_scratch_root`` only when the entry is a record --
    supplied (this keyword, else ``OMNIDRIVER_SCRATCH_DIR``) or refused by
    name, never defaulted under ``cases_root``.

    Resolves ``entry`` to a spec via ``load_entry_spec`` (which refuses a
    tutorial_record by name), then delegates every diagnostic/run-document
    assembly step to :func:`_strict_plan_for_spec`. A caller that already
    has a spec built some other way (a tutorial-record case, whose spec
    ``record_execution.record_case_spec`` builds directly, with no registry
    entry to resolve) calls :func:`_strict_plan_for_spec` itself instead,
    reusing the same diagnostics/run-document pipeline.
    """
    incoming_overrides = dict(overrides or {})
    cases_root_value = incoming_overrides.get("cases_root")
    cases_root = Path(cases_root_value) if cases_root_value is not None else None
    # A tutorial record is dispatched explicitly, the same way
    # `sweep_runner._sweep_record` dispatches one out of a sweep -- never
    # tried as a factory/case-folder entry first via `load_entry_spec`
    # (which refuses a record by name).
    classification = classify_entry(
        entry, entry_kind=entry_kind, cases_root=cases_root, driver_context=driver_context,
    )
    if classification.kind == "tutorial_record":
        return _strict_plan_for_record(
            classification.record,
            entry=entry,
            entry_kind=entry_kind,
            cases_root=cases_root,
            overrides=incoming_overrides,
            config_path=config_path,
            environment_source=environment_source,
            allow_unresolved_configuration=allow_unresolved_configuration,
            scratch_root=scratch_root,
            cli_study=cli_study,
            inputs=inputs,
            driver_context=driver_context,
        )
    refuse_cli_study_for_non_record(entry, cli_study)
    if inputs:
        raise TutorialRecordError(
            f"--input applies only to a tutorial record's run, and {entry!r} is not a "
            "tutorial record"
        )
    spec = load_entry_spec(
        entry,
        entry_kind=entry_kind,
        overrides=overrides,
        driver_context=driver_context,
    )
    return _strict_plan_for_spec(
        entry,
        spec,
        entry_kind=entry_kind,
        environment_source=environment_source,
        allow_unresolved_configuration=allow_unresolved_configuration,
        driver_context=driver_context,
        config_path=config_path,
    )


def refuse_cli_study_for_non_record(entry: str, cli_study: Mapping[str, Any] | None) -> None:
    """A CLI study value (``--parallel``) asks something of a tutorial
    record's run; a factory or case-folder entry has no record study to put
    it in, so it is refused by name rather than dropped."""
    if cli_study:
        flags = ", ".join(f"--{name}" for name in sorted(cli_study))
        raise TutorialRecordError(
            f"{flags} applies only to a tutorial record's run, and {entry!r} is not a "
            "tutorial record"
        )


def _strict_plan_for_record(
    record: Any,
    *,
    entry: str,
    entry_kind: str | None,
    cases_root: Path | None,
    overrides: dict[str, Any],
    config_path: str | Path | None,
    environment_source: str | None,
    allow_unresolved_configuration: bool,
    scratch_root: str | Path | None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> StrictPlanReport:
    """Plan (and commit) one tutorial-record case for `plan --strict --entry
    <record>` / `step`/`run --entry <record>`.

    A record has no ambient cases root, so it must be supplied (the same
    refusal `sweep_runner._sweep_record` raises for a swept record).
    Everything in ``overrides`` other than ``cases_root`` is this single,
    non-swept case's own study values (``base``, no ``sweep`` values -- one
    resolved case, no axis expansion). The case is staged and committed via
    the same shared ``commit_and_build_record_spec`` sequence `sweep_runner`
    also calls.

    There is no sweep output_dir here to stage under, so this stages under
    the supplied scratch root (``scratch_root``, else
    ``OMNIDRIVER_SCRATCH_DIR``, else refused by name;
    `core.specs.paths.resolve_scratch_root`), under a `records/<name>`
    subdirectory -- distinct from `cli._context_from_entry`'s `runs/<name>`
    staging for a case-folder entry, so a record and a same-named case
    folder can never collide (`registry.classify_entry`'s invariant). A
    scratch root inside `cases_root` is refused.

    The plan this returns commits the record's case as a side effect and
    persists the resulting `RunDocument` to `<output_dir>/run_document.json`
    -- the exact path `_run_launch_description`'s record branch advertises
    as `run --run-document <path>` -- so that advertised command is
    immediately runnable.
    """
    if cases_root is None:
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be planned: 'cases_root' must "
            "name where its native case lives (there is no ambient cases "
            "root to discover); supply --cases-root or OMNIDRIVER_CASES_ROOT"
        )
    study_by_source = {
        "base": {
            key: value for key, value in overrides.items() if key != "cases_root"
        },
        "sweep": {},
        "cli": dict(cli_study or {}),
    }
    # Resolved here, after the cases_root refusal and only for a record --
    # lazily, so nothing else ever asks for a scratch root it does not use.
    resolved_scratch_root = resolve_scratch_root(scratch_root, cases_root=cases_root)
    staged_case_root = resolved_scratch_root / "records" / record.name
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
        # A read-only scratch root is refused by name rather than raising a
        # raw traceback; since the root is always supplied, this only fires
        # when the supplied root cannot be written.
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be staged under {staged_case_root}: {exc}. "
            "Supply a writable scratch root outside the cases root with "
            "--scratch-dir (or OMNIDRIVER_SCRATCH_DIR)"
        ) from exc
    report = _strict_plan_for_spec(
        entry,
        spec,
        entry_kind=entry_kind,
        config_path=config_path,
        environment_source=environment_source,
        allow_unresolved_configuration=allow_unresolved_configuration,
        driver_context=driver_context,
        scan_cache_root=resolved_scratch_root,
    )
    run_document_path = Path(report.launch["output_dir"]) / RUN_DOCUMENT_FILENAME
    run_document_path.parent.mkdir(parents=True, exist_ok=True)
    run_document_path.write_text(json.dumps(report.run_document.to_json(), indent=2))
    return report


def _strict_plan_for_spec(
    entry: str,
    spec: Any,
    *,
    entry_kind: str | None = None,
    config_path: str | Path | None = None,
    environment_source: str | None = None,
    allow_unresolved_configuration: bool = False,
    driver_context: "DriverContext",
    scan_cache_root: Path | None = None,
) -> StrictPlanReport:
    """The diagnostics/run-document assembly ``strict_plan`` performs, taking
    an already-resolved ``spec`` directly rather than resolving ``entry``
    itself -- so a caller whose spec did not come from the registry (a
    tutorial-record case) can reuse this pipeline without a second runner.
    """
    execution_context = resolve_execution_context(spec)
    is_tutorial_record = bool(
        spec.metadata and spec.metadata.get("resolution") == "tutorial_record"
    )
    launch = _run_launch_description(
        entry,
        execution_context,
        driver_context=driver_context,
        entry_kind=entry_kind,
        config_path=config_path,
        allow_unresolved_configuration=allow_unresolved_configuration,
        is_tutorial_record=is_tutorial_record,
    )
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
    run_document, validation_diagnostics = _run_document_from_case(
        entry=entry,
        spec=spec,
        launch=launch,
        workflow_dag=workflow_dag,
        workflow_state=workflow_state,
        expected_artifacts=artifacts,
        driver_context=driver_context,
    )
    catalog_diagnostics = _catalog_diagnostics(driver_context, scan_cache_root=scan_cache_root)
    artifact_diagnostics = _artifact_diagnostics(
        spec, artifacts, workflow_dag, driver_context,
    )
    env_diagnostics = driver_context.capabilities.environment_preflight.diagnostics(
        workflow_dag,
        environment_source=environment_source,
        driver_context=driver_context,
    )
    # Bound once and passed on: the audit needs to know *why* mesh
    # diagnostics are empty -- an exempt case produces the same empty tuple
    # as a mesh that was examined and found clean.
    mesh_geometry_exempt = _mesh_geometry_exempt(spec, driver_context)
    mesh_diagnostics = _mesh_geometry_diagnostics(
        spec.case_root,
        exempt=mesh_geometry_exempt,
        driver_context=driver_context,
    )
    configuration_evidence = driver_context.capabilities.effective_configuration.inspect(
        case_root=Path(spec.case_root),
        driver_context=driver_context,
        execution_env=dict(os.environ),
    )
    configuration_diagnostics = _configuration_evidence_diagnostics(
        configuration_evidence,
        allow_unresolved_configuration=allow_unresolved_configuration,
    )
    configuration_evidence_policy = (
        "exploratory" if allow_unresolved_configuration else "strict"
    )
    simulation_audit, readiness_score = _build_simulation_audit(
        spec=spec,
        driver_context=driver_context,
        workflow_dag=workflow_dag,
        artifacts=artifacts,
        validation_diagnostics=validation_diagnostics,
        workflow_diagnostics=workflow_diagnostics,
        artifact_diagnostics=artifact_diagnostics,
        environment_diagnostics=env_diagnostics,
        mesh_geometry_diagnostics=mesh_diagnostics,
        mesh_geometry_exempt=mesh_geometry_exempt,
        required_case_files=tuple(
            rule.path
            for rule in driver_context.capabilities.cxx_mapping.profile().case_files
            if rule.required == "always"
        ),
    )
    plan_diagnostics = (
        validation_diagnostics
        + workflow_diagnostics
        + catalog_diagnostics
        + artifact_diagnostics
        + mesh_diagnostics
        + configuration_diagnostics
    )
    # The plugin owns solver capabilities and model-specific field exposure.
    # Keep the established payload shape for cardiacFoam compatibility while
    # attaching the immutable identity that supplied it.
    raw_capability_manifest = dict(driver_context.capabilities.manifest.manifest())
    raw_capability_manifest["plugin_identity"] = driver_context.identity.to_json()
    capability_manifest = _jsonable(raw_capability_manifest)
    function_object_diagnostics = driver_context.capabilities.dict_diagnostics.function_object_fields(
        spec.case_root,
        samplable=raw_capability_manifest.get("samplable_fields", {}),
    )
    case_dict_key_diagnostics = driver_context.capabilities.dict_diagnostics.case_dict_keys(
        spec.case_root,
        catalogued_paths=_catalogued_paths(
            driver_context.capabilities.dictionaries.entries()
        ),
        dict_relpaths=_owned_dict_relpaths(spec, driver_context),
    )
    # Field and case-key diagnostics are warn-only: reported (in
    # all_diagnostics) but never part of plan_diagnostics, so neither a
    # sampled-field nor an uncatalogued-key warning can fail a plan. The
    # catalogue does not own every key that may legitimately appear in a case
    # dictionary, so an unmatched key is a question for a human, not a defect.
    all_diagnostics = (
        plan_diagnostics
        + env_diagnostics
        + function_object_diagnostics
        + case_dict_key_diagnostics
    )
    failed = _has_error(plan_diagnostics)
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
        status="failed" if failed else "ok",
        entry=entry,
        resolved_entry={
            "entry_name": spec.metadata.get("entry_name", entry),
            "entry_kind": spec.metadata.get("entry_kind"),
            "entry_path": spec.metadata.get("entry_path"),
            "source_type": spec.metadata.get("source_type"),
            "workflow_family": spec.metadata.get("workflow_family"),
        },
        readiness_score=readiness_score,
        simulation_audit=simulation_audit,
        validation_diagnostics=validation_diagnostics,
        workflow_diagnostics=workflow_diagnostics,
        catalog_coverage_errors=catalog_diagnostics,
        artifact_diagnostics=artifact_diagnostics,
        environment_diagnostics=env_diagnostics,
        mesh_geometry_diagnostics=mesh_diagnostics,
        launch=launch,
        workflow_dag=workflow_dag,
        workflow_state=workflow_state,
        expected_artifacts=artifacts,
        run_document=run_document,
        capability_manifest=capability_manifest,
        function_object_diagnostics=function_object_diagnostics,
        case_dict_key_diagnostics=case_dict_key_diagnostics,
        configuration_evidence=configuration_evidence,
        configuration_evidence_policy=configuration_evidence_policy,
        configuration_diagnostics=configuration_diagnostics,
        plugin=driver_context.identity.to_json(),
    )
