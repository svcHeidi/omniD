from __future__ import annotations

import fnmatch
import os
import shlex
import sys
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


import shutil

from .runtime.artifacts import predict_data_artifacts
from .runtime.execution_context import resolve_execution_context
from .runtime.models import DataArtifact
from .runtime.registry import load_entry_spec
from .runtime.run_document_adapter import _run_document_from_case
from .runtime.run_model import RunDocument
from .runtime.strict_audit import _build_simulation_audit
from .runtime.workflow import (
    WorkflowDiagnostic,
    _unwrap_mpi_program,
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
from .compatibility import legacy_dict_key_scanner
from .contracts.catalogue_paths import catalogued_paths as _catalogued_paths


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


def _repo_root_from_here() -> Path | None:
    """Return the monorepo root, or None when running in a standalone install.

    Mirrors the three-tier logic in ``specs/paths.py:repo_root_default()``.
    Returns ``None`` instead of raising so that callers can gracefully skip
    operations that require the full source tree (e.g. dict-key scanning).
    """
    current = Path(__file__).resolve()
    tier2_candidate: Path | None = None
    for parent in current.parents:
        has_src = (parent / "src").exists()
        has_tutorials = (parent / "tutorials").exists()
        if has_src and has_tutorials:   # Tier 1: full monorepo
            return parent
        if has_tutorials and tier2_candidate is None:  # Tier 2: tutorials-only
            tier2_candidate = parent
    return tier2_candidate  # Tier 3: fully standalone → None


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

    Only dictionaries the catalogue covers may be swept: warning about keys in
    a file the catalogue never claimed to describe would be pure noise.

    The spec's own generic ``dict_file_relpaths`` metadata is authoritative
    when present. Older adapters may still expose ``*_relpath`` metadata; the
    suffix-based compatibility read keeps that surface generic. A bare case
    folder has no metadata, so the plugin's document names are matched against
    the adapter's declared case-file rules. Core never supplies a directory
    layout or document vocabulary.
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
    documents = driver_context.capabilities.override_schema.dict_entry_catalog()
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


def _catalog_diagnostics(driver_context: "DriverContext") -> tuple[StrictDiagnostic, ...]:
    """Run only the resolved cxx_mapping provider's reviewed C++<->Python
    mapping checks."""

    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    if mapping is None:
        return ()
    # A diagnostic's `source=` names what reported it, not the whole stack --
    # `StackIdentity` has no singular id to fall back on. `resolutions()`
    # already records, per capability, which provider answered it; the
    # provider that answered `cxx_mapping` is exactly the one whose profile
    # supplied `mapping` above, so its plugin_id is the correct "what
    # reported this" answer, not an arbitrary stand-in such as the
    # most-specific provider or the stack's capability_digest.
    cxx_mapping_source = driver_context.identity.resolutions.get(
        "cxx_mapping", "cxx_mapping",
    )
    strict_dict_key_report = legacy_dict_key_scanner()
    diagnostics: list[StrictDiagnostic] = []
    for source_root in mapping.source_roots:
        if not source_root.is_dir():
            diagnostics.append(_diagnostic(
                "warning",
                "plugin_cxx_source_unavailable",
                f"Plugin C++ source root is unavailable: {source_root}",
                source=cxx_mapping_source,
            ))
            continue
        report = strict_dict_key_report(
            source_root,
            allowlist_path=mapping.allowlist_path,
            entries=driver_context.capabilities.dictionaries.entries(),
        )
        payload = report.to_json()
        for key in ("unmatched_cxx_reads", "stale_paths", "unmatched_subdicts", "unused_allowlist"):
            for item in payload[key]:
                diagnostics.append(_diagnostic(
                    "error",
                    f"plugin_dict_key_{key}",
                    f"Plugin C++/catalog scanner reported {key}: {item}",
                    source=f"{cxx_mapping_source}:{source_root}",
                ))
    return tuple(diagnostics)


def _is_nondimensional_entry(spec, driver_context: "DriverContext") -> bool:
    """Return True when the SI mesh-scale gate is not meaningful."""
    entry_name = ""
    family = ""
    if spec.metadata:
        entry_name = str(spec.metadata.get("entry_name", "") or "")
        family = str(spec.metadata.get("workflow_family", "") or "")
    haystack = f"{entry_name} {family}".lower()
    if "manufactured" in haystack or "verification" in haystack:
        return True
    return driver_context.capabilities.mesh_diagnostic_policy.is_nondimensional(spec)


def _mesh_geometry_diagnostics(
    case_root: str | Path,
    *,
    exempt: bool = False,
    driver_context: "DriverContext",
) -> tuple[StrictDiagnostic, ...]:
    """Adapt mesh-scale detection into StrictDiagnostics for the report.

    Core classifies every polyMesh region's scale; the active plugin may add
    checks for point sets that are not mesh regions (cardiacFoam's
    ``constant/purkinjeGraph*``). Both report under the same
    ``mesh_geometry`` source, and both are skipped by the same exemption.
    """
    if exempt or "SKIP_MESH_DIAGNOSTICS" in os.environ:
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
    entry_kind: str | None,
    config_path: str | Path | None,
    allow_unresolved_configuration: bool = False,
) -> dict[str, Any]:
    """Describe the modern `run --strict --entry` invocation for this plan.

    Replaces strict_plan's former reuse of describe_launch("sim", ...):
    that call re-resolved the entry a second time (strict_plan already has
    `spec` from load_entry_spec) purely to read these four paths off it, and
    tied the strict/workflow-DAG path -- which never runs the legacy
    sim/post/all CLI at all -- to describe_launch's action vocabulary.
    `run --strict --entry` is the command that actually executes this exact
    plan today.
    """
    command = [sys.executable, "-m", "omnidriver", "run", "--strict", "--entry", entry]
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
        "workflow_state_path": str(context.workflow_state_path),
        "case_root": str(context.case_root),
        "setup_root": str(context.setup_root),
        "output_dir": str(context.output_dir),
    }


def strict_plan(
    entry: str,
    *,
    entry_kind: str | None = None,
    overrides: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    explicit_bashrc: str | Path | None = None,
    allow_unresolved_configuration: bool = False,
    driver_context: "DriverContext",
) -> StrictPlanReport:
    """Build a non-mutating strict simulation plan report."""
    spec = load_entry_spec(
        entry,
        entry_kind=entry_kind,
        overrides=overrides,
        driver_context=driver_context,
    )
    execution_context = resolve_execution_context(spec)
    launch = _run_launch_description(
        entry,
        execution_context,
        entry_kind=entry_kind,
        config_path=config_path,
        allow_unresolved_configuration=allow_unresolved_configuration,
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
    catalog_diagnostics = _catalog_diagnostics(driver_context)
    artifact_diagnostics = _artifact_diagnostics(
        spec, artifacts, workflow_dag, driver_context,
    )
    env_diagnostics = driver_context.capabilities.environment_preflight.diagnostics(
        workflow_dag,
        explicit_bashrc=str(explicit_bashrc) if explicit_bashrc is not None else None,
        driver_context=driver_context,
    )
    # Bound once and passed on: the audit has to know *why* the mesh
    # diagnostics are empty. An exempt case (no physical scale, or a generic
    # case whose conventions core does not know) produces the same empty tuple
    # as a mesh that was examined and found clean, and used to be scored the
    # same way.
    mesh_geometry_exempt = (
        _is_nondimensional_entry(spec, driver_context)
        or bool(spec.metadata.get("generic_case"))
    )
    mesh_diagnostics = _mesh_geometry_diagnostics(
        spec.case_root,
        exempt=mesh_geometry_exempt,
        driver_context=driver_context,
    )
    configuration_evidence = driver_context.capabilities.override_scopes.inspect(
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
    simulation_audit, generation_diagnostics, readiness_score = _build_simulation_audit(
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
        generation_diagnostics
        + validation_diagnostics
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
