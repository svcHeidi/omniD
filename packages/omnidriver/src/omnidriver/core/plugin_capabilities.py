"""Focused capability interfaces and adapters for solver plugins.

Core consumers use :class:`PluginCapabilities` instead of calling
``DriverContext.plugin`` directly. Required plugin methods are exposed
directly; optional hooks have an explicit default or refusal behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_interface import SolverPlugin
    from .plugin_profile import CaseFileRule
    from .runtime.models import DataArtifact, TutorialSpec
    from omnidriver.core.planning_types import StrictDiagnostic
    from omnidriver.core.report_catalog import ReportDefinition


@dataclass(frozen=True)
class ConfigurationValidationRequest:
    """Input to :class:`ConfigurationValidatorCapability`: the resolved spec
    whose configuration the plugin should judge."""

    spec: "TutorialSpec"


@dataclass(frozen=True)
class RunSemanticValidationRequest:
    """Input to :class:`RunSemanticValidatorCapability`: the loose run-context
    mapping assembled at execution time, not a resolved ``TutorialSpec``."""

    context: dict[str, Any]


@dataclass(frozen=True)
class ArtifactPredictionRequest:
    """Input to :class:`ArtifactPredictorCapability`: the case to inspect and
    the spec it was built from. May name a case that does not exist yet."""

    case_root: Path
    spec: "TutorialSpec"


@dataclass(frozen=True)
class RunDocumentConfigurationRequest:
    """Input to :class:`RunDocumentConfigurationCapability`: the spec whose
    plugin-owned RunDocument ``config`` object is to be built."""

    spec: "TutorialSpec"


@dataclass(frozen=True)
class CaseCompatibilityRequest:
    """Input to :class:`CaseCompatibilityCapability`: the case folder to judge
    by filesystem evidence, before any dictionary is parsed."""

    case_root: Path


@dataclass(frozen=True)
class SweepRoutingRequest:
    """Input to :class:`SweepMaterializerCapability` ``route``: the sweep's
    static base values plus one expanded axis combination from core."""

    base: dict[str, Any]
    resolved_axis_values: dict[str, Any]


@dataclass(frozen=True)
class SweepMaterializationRequest:
    """Input to :class:`SweepMaterializerCapability` ``materialize``: where to
    write, and the routed values ``route`` produced for this case."""

    case_dir: Path
    routed: dict[str, Any]


@dataclass(frozen=True)
class ResolvedInput:
    """One field-level input a solver plugin's case model resolves to an
    actual on-disk path -- or fails to.

    Globs are insufficient here: field *names* are adapter-configurable and
    field *locations* may resolve through a runtime-specific search, so a
    field's canonical path is not knowable from its name alone. ``consumer``
    records which model/domain
    resolved it, for diagnostics -- never for severity.
    """

    name: str
    path: Path | None
    required: bool
    consumer: str


@dataclass(frozen=True)
class CaseRuntimeConventions:
    """Environment-declared paths that are generated during a case run.

    Core supplies copying, snapshotting, collision detection, and recovery.
    It does not supply names such as ``postProcessing`` or rules for numeric
    time directories. A missing declaration is deliberately neutral: no
    authored path is silently removed from a staged case.
    """

    output_collection_relpath: str | None = None
    generated_directory_names: tuple[str, ...] = ()
    generated_file_names: tuple[str, ...] = ()
    generated_directory_prefixes: tuple[str, ...] = ()
    generated_file_prefixes: tuple[str, ...] = ()
    generated_file_suffixes: tuple[str, ...] = ()
    preserved_file_suffixes: tuple[str, ...] = ()
    generated_case_markers: tuple[str, ...] = ()
    case_entrypoints: tuple[str, ...] = ()
    case_script_commands: tuple[str, ...] = ()
    case_discovery_ignored_directory_names: tuple[str, ...] = ()
    decomposition_directory_prefix: str | None = None
    time_directory_name_pattern: str | None = None
    preserved_time_directory_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeDependency:
    """One thing the workflow's *executable* consumes at run time, outside
    the case tree: the solver binary itself, a library it links or loads,
    or a case-local shared object built from sources inside the case.

    Replaces the earlier ``extra_provenance_paths() -> tuple[Path, ...]``
    stub, which could not express "this was required and I could not find
    it" -- a tuple of paths can only omit, and omission reads as "nothing to
    check". ``path is None`` on a ``required=True`` dependency must surface
    as ``unavailable`` rather than silently vanishing from the list.

    A workflow step may run through a case-local entrypoint, so its command
    fingerprints that entrypoint, never an unobserved binary it invokes --
    the exact gap that let a rebuilt solver replay a resumed
    run's previous numbers as fresh. Declaring dependencies this way, apart
    from however a step happens to be launched, is the fix.
    """

    name: str
    path: Path | None
    required: bool


class TutorialCatalogCapability(Protocol):
    """The tutorials this plugin registers, and how to display them.

    ``catalog`` returns the plugin's registry keyed by tutorial name -- the
    entry names ``omnidriver`` accepts. ``displays`` returns the presentation
    metadata ``describe`` renders. Both are required v1 members, so there is
    no fallback: a plugin that registers no tutorials returns empty rather
    than omitting the member.

    :adapts: get_tutorial_catalog, get_tutorial_displays
    :consumed-by: omnidriver/core/runtime/registry.py, omnidriver/cardiacfoam/dict_builder.py
    :fallback: none
    :status: mandatory
    """

    def catalog(self) -> dict[str, Any]: ...
    def displays(self) -> tuple[Any, ...]: ...


class DictionaryCatalogCapability(Protocol):
    """The plugin's dictionary vocabulary, in three shapes for three callers.

    ``entries`` is the flat tuple of ``DictEntry`` values; ``catalog`` is the
    same data as a queryable ``DictionaryCatalog`` (``entries_for(document)``);
    ``groups`` buckets entries by the plugin's own document names. Core does
    not know those names -- ``electroProperties`` is cardiac vocabulary, and a
    solids4foam plugin would say ``solidProperties`` instead.

    All three are required v1 members with no fallback. This is the seam that
    keeps dictionary *syntax* knowledge (core's) apart from dictionary
    *meaning* (the plugin's).

    :adapts: get_dict_entries, get_dict_groups, get_dictionary_catalog, get_phases
    :consumed-by: omnidriver/dict_entries.py, omnidriver/cardiacfoam/sweep.py, omnidriver/openfoam/apply_overrides.py, omnidriver/openfoam/dict_builder.py, omnidriver/core/specs/validation.py, omnidriver/core/strict_planning.py
    :fallback: legacy_phases
    :status: mixed
    """

    def entries(self) -> tuple[Any, ...]: ...
    def catalog(self) -> Any: ...
    def groups(self) -> dict[str, tuple[Any, ...]]: ...
    def phases(self) -> tuple[str, ...]: ...


class CapabilityManifestCapability(Protocol):
    """The plugin's self-description of what it can model.

    Deliberately untyped at the core boundary: ``CapabilityManifest`` in
    ``plugin_interface`` is an empty Protocol, because the axes a plugin
    advertises are its own (cardiacFoam declares ionic models and solvers; a
    different plugin would declare something else entirely). Core namespaces
    and serialises it for ``describe`` without interpreting it.

    :adapts: get_capabilities
    :consumed-by: omnidriver/dict_entries.py, omnidriver/core/introspection.py, omnidriver/core/strict_planning.py
    :fallback: none
    :status: mandatory
    """

    def manifest(self) -> Any: ...


class ConfigurationValidatorCapability(Protocol):
    """Plan-time validation of a resolved tutorial spec, in the plugin's terms.

    Returns ``StrictDiagnostic`` values rather than raising, so the strict
    planner can report every problem in one pass instead of stopping at the
    first -- the property that lets an agent self-heal a case in one edit
    round. An empty tuple means "nothing this plugin can object to", never
    "not checked".

    :adapts: validate_configuration
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: none
    :status: mandatory
    """

    def validate(
        self, request: ConfigurationValidationRequest,
    ) -> tuple["StrictDiagnostic", ...]: ...


class RunSemanticValidatorCapability(Protocol):
    """Validation of a run's semantics, as opposed to its configuration.

    Distinct from :class:`ConfigurationValidatorCapability`: that one judges a
    ``TutorialSpec``, this one judges a looser run context dictionary at
    execution time. Required v1 member, no fallback.

    :adapts: validate_run_semantics
    :consumed-by: omnidriver/core/specs/validation.py
    :fallback: none
    :status: mandatory
    """

    def validate(self, request: RunSemanticValidationRequest) -> tuple[Any, ...]: ...


class ArtifactPredictorCapability(Protocol):
    """What files this case will produce, predicted before it runs.

    The prediction is a contract: the strict runner compares it against what
    actually appeared and fails with ``missing_expected_artifacts`` on a
    mismatch, which is how a silently-not-writing solver gets caught.

    That makes the predictor's honesty load-bearing. It must never raise --
    agents call it against partly-mutated cases -- and it must distinguish
    "I could not determine the exports" from "the exports are declared
    empty". Conflating those two through a falsy empty tuple is a real defect
    this code has already had.

    :adapts: predict_data_artifacts
    :consumed-by: omnidriver/core/runtime/artifacts.py
    :fallback: none
    :status: mandatory
    """

    def predict(self, request: ArtifactPredictionRequest) -> tuple["DataArtifact", ...]: ...


class RunDocumentConfigurationCapability(Protocol):
    """The plugin's half of a RunDocument: its ``config`` object and schema.

    ``schemas/run-document.json`` declares ``config`` as an open object
    (``additionalProperties: true``) with no fixed key set, so the whole
    vocabulary inside it belongs to the plugin. ``build`` produces the object
    and any diagnostics; ``schema`` produces the JSON Schema core validates it
    against dynamically, turning a plugin's own rules into structured
    diagnostics an agent can act on.

    The fallback returns an empty config. It must not invent a phase or
    configuration vocabulary for an adapter that did not declare one.

    :adapts: build_run_document_config, get_run_document_config_schema
    :consumed-by: omnidriver/core/runtime/run_document_adapter.py, omnidriver/core/runtime/run_document_exec.py
    :fallback: legacy_run_document_config
    :status: mixed
    """

    def build(
        self, request: RunDocumentConfigurationRequest,
    ) -> tuple[dict[str, dict[str, Any]], tuple["StrictDiagnostic", ...]]: ...
    def schema(self) -> dict[str, Any]: ...


class CxxMappingCapability(Protocol):
    """The plugin's declarative profile: case-file rules and C++ provenance.

    Sourced from the plugin's ``plugin.yaml`` via ``get_profile()``. Named for
    the C++ source mapping it carries (which solver sources back which
    dictionary keys, used for provenance fingerprinting), but the same profile
    also backs :class:`CaseFileContractCapability`.

    :adapts: get_profile
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: none
    :status: mandatory
    """

    def profile(self) -> Any: ...


class DictDiagnosticsCapability(Protocol):
    """Warn-only checks of a case's on-disk dict files against declared
    vocabulary: sampled fields absent from the capability manifest, and dict
    keys absent from the plugin's catalogue.

    The selected adapter parses its own configuration format. These
    diagnostics are included in ``all_diagnostics`` but do not invalidate a
    plan.

    :adapts: get_function_object_field_diagnostics, get_case_dict_key_diagnostics
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: legacy_function_object_field_diagnostics, legacy_case_dict_key_diagnostics
    :status: optional
    """

    def function_object_fields(
        self, case_root: Path, *, samplable: dict[str, Any],
    ) -> tuple[Any, ...]: ...

    def case_dict_keys(
        self,
        case_root: Path,
        *,
        catalogued_paths: Any,
        dict_relpaths: tuple[str, ...],
    ) -> tuple[Any, ...]: ...


class MeshDiagnosticPolicyCapability(Protocol):
    """Plugin-owned exemptions from, and additions to, core's mesh diagnostics.

    Core applies the generic mesh-diagnostics lifecycle. The active adapter
    supplies the geometry interpretation, non-dimensional exemptions, and
    any additional geometry that is not part of the base environment format.

    ``is_nondimensional`` falls back to ``False``, which keeps diagnostics on
    when an adapter has not declared an exemption.

    ``base_geometry_diagnostics`` is the classification itself -- despite the
    class docstring above, it was never actually core's own logic; it's
    OpenFOAM-specific (``polyMesh`` region parsing), so it has to be
    plugin-routed like everything else here, not called directly by core.

    :adapts: get_mesh_geometry_diagnostics, get_base_mesh_geometry_diagnostics, is_nondimensional_case
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: legacy_nondimensional_case, legacy_base_mesh_geometry_diagnostics
    :status: optional
    """

    def is_nondimensional(self, spec: "TutorialSpec") -> bool: ...
    def extra_geometry_diagnostics(self, case_root: Path) -> tuple[Any, ...]: ...
    def base_geometry_diagnostics(self, case_root: Path) -> tuple[Any, ...]: ...


class CaseCompatibilityCapability(Protocol):
    """Whether a case folder on disk belongs to this plugin, and whether it
    can run without driver-owned workflow metadata.

    Both questions are answered from filesystem evidence alone, before any
    dictionary is parsed, so the adapter owns the case markers and the
    no-workflow run policy. Core first checks an adapter-declared entrypoint;
    the fallback returns ``False``.

    :adapts: has_case_marker, is_case_runnable_without_workflow
    :consumed-by: omnidriver/core/runtime/registry.py
    :fallback: legacy_case_marker, legacy_case_runnable_without_workflow
    :status: optional
    """

    def has_case_marker(self, request: CaseCompatibilityRequest) -> bool: ...
    def is_runnable_without_workflow(self, request: CaseCompatibilityRequest) -> bool: ...


class SweepMaterializerCapability(Protocol):
    """How one resolved sweep-axis combination becomes a runnable case.

    Core owns sweep *expansion* -- ``sweep_expansion.py`` computes the
    cross-product or zip of axes, validates lengths, and caps case counts
    without knowing what any axis means. This capability owns what a resolved
    combination *is*: which of the plugin's dictionaries and keys each axis
    lands in, and how the case is written.

    The split between the two methods is pure/impure, not two kinds of sweep.
    ``route`` is a total function from axis values to a routed mapping and
    must not touch the filesystem, which is what makes ``sweep-plan``
    non-destructive; ``materialize`` does every write.

    Uniquely among these capabilities, the fallback cannot be neutral. An
    empty routing would silently yield a case that is not the one the sweep
    asked for, so an adapter without these hooks is refused by name instead.
    This prevents one adapter's materializer from running for another.

    :adapts: materialize_sweep_case, route_sweep_case_values
    :consumed-by: omnidriver/sweep_materialize.py, omnidriver/sweep_routing.py
    :fallback: legacy_materialize_sweep_case, legacy_route_sweep_case
    :status: optional
    """

    def route(self, request: SweepRoutingRequest, *, driver_context: Any) -> dict[str, Any]: ...
    def materialize(self, request: SweepMaterializationRequest) -> None: ...


class CommandAuthorizationCapability(Protocol):
    """What the active plugin authorizes a workflow step to invoke.

    ``solver_commands`` and ``auxiliary_commands`` are both authorized, but
    only ``solver_commands`` names binaries that produce a run's artifacts;
    core's artifact-producer heuristic must consult that one alone.

    ``environment_commands`` is a declaration from the execution environment,
    not from solver semantics.  ``is_installed_environment_command`` permits
    the adapter to recognize runtime-discovered applications without exposing
    its environment variables to Core.

    :adapts: get_auxiliary_commands, get_environment_commands, get_solver_commands, get_utility_manifests, get_utility_roots, is_installed_environment_command
    :consumed-by: omnidriver/core/runtime/artifacts.py, omnidriver/core/runtime/workflow.py, omnidriver/core/strict_planning.py
    :fallback: legacy_environment_commands, legacy_is_installed_environment_command
    :status: mixed
    """

    def solver_commands(self) -> frozenset[str]: ...
    def auxiliary_commands(self) -> frozenset[str]: ...
    def environment_commands(self) -> frozenset[str]: ...
    def is_installed_environment_command(self, command: str) -> bool: ...
    def utility_manifests(self) -> dict[str, Any]: ...
    def utility_roots(self) -> tuple[Path, ...]: ...


class CaseIntrospectionCapability(Protocol):
    """Solver-specific case-model resolution and the fields it exposes.

    ``resolve_case_models`` is a best-effort, never-raising read of a case's
    on-disk configuration; ``samplable_fields`` names the fields the resolved
    model exposes for sampling by function objects, split by region. A
    plugin with no solver semantics (the generic plugin) resolves nothing and
    exposes no fields.

    ``selected_start_time`` answers which on-disk state directory a run
    resumes from. It is an environment interpretation, not a Core path rule:
    an adapter that has no such convention returns ``None`` and Core does not
    invent a directory to fingerprint.

    :adapts: get_samplable_fields, get_selected_start_time, resolve_case_models
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: none
    :status: mixed
    """

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]: ...
    def samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]: ...
    def selected_start_time(
        self, case_root: Path, resolved_case: dict[str, Any], *, driver_context: Any,
    ) -> str | None: ...


class CaseFileContractCapability(Protocol):
    """Which case files the active plugin's profile declares, and how strictly.

    Sourced directly from ``PluginProfile.case_files``: ``required_files``
    lists every rule whose ``required`` is ``"always"``; ``conditional_files``
    lists the rest. ``required_rules`` returns the same required rules with
    their ``role`` intact.

    **Roles are namespaced and the prefix is load-bearing.** Core owns only
    its documented namespaces; every other namespace belongs to the adapter.
    For example, the OpenFOAM adapter uses ``openfoam.*`` and the solver may
    use ``plugin.*``. Consumers classify ownership from the namespace, not
    from a hard-coded file path. ``get_profile()`` is a required v1 member, so
    every adapter carries this data and no compatibility fallback is needed.

    ``describe_config_resolution`` is different: it is a human-readable
    sentence, not derived from ``case_files`` data, so it uses the
    compatibility fallback only when an adapter has not authored one.

    ``all_rules`` returns every declared rule regardless of ``required``
    status, since a file can legitimately be conditional rather than always
    required.

    :adapts: get_profile, get_config_resolution_description
    :consumed-by: omnidriver/core/runtime/strict_audit.py, omnidriver/core/tutorial_contracts.py, omnidriver/core/runtime/provenance_inputs.py
    :fallback: legacy_describe_config_resolution
    :status: mixed
    """

    def required_files(self) -> tuple[str, ...]: ...
    def conditional_files(self) -> tuple[str, ...]: ...
    def required_rules(self) -> tuple["CaseFileRule", ...]: ...
    def all_rules(self) -> tuple["CaseFileRule", ...]: ...
    def describe_config_resolution(self) -> str: ...
class CaseRuntimeConventionsCapability(Protocol):
    """Generated-path and output-root declarations for one environment.

    A staging transaction needs to distinguish reusable authored inputs from
    derived output, and an entry-mode sweep may need to snapshot one shared
    output tree between cases. Those are Core mechanisms. The path names are
    environment conventions, so this capability supplies them as data. A
    plugin without the optional hook receives an empty declaration: Core
    preserves every path and does not collect a convention-specific tree.

    :adapts: get_case_runtime_conventions
    :consumed-by: omnidriver/core/runtime/registry.py, omnidriver/core/runtime/sweep_runner.py
    :fallback: legacy_case_runtime_conventions
    :status: optional
    """

    def conventions(self) -> CaseRuntimeConventions: ...


class EnvironmentPreflightCapability(Protocol):
    """Preflight the runtime environment a plan's workflow_dag will execute in.

    Sourcing a bashrc, checking ``$FOAM_APPBIN``-style env vars, and
    resolving executables on PATH are all environment-specific -- a FEniCS
    plugin's preflight would source a Python venv and check for MPI, not
    ``WM_PROJECT_DIR``. Core only knows it needs an answer before launch.

    ``configure`` applies the plugin's environment contract (e.g. an
    already-sourced OpenFOAM environment plus any plugin-specific overlay)
    without re-sourcing anything, returning the resolved variable mapping.

    ``diagnostics`` and ``load`` accept an explicit environment-sourcing
    script through ``explicit_bashrc``. The corresponding CLI option is
    ``--environment-bashrc``.

    :adapts: get_environment_diagnostics, get_configured_environment, get_loaded_environment
    :consumed-by: omnidriver/core/strict_planning.py, omnidriver/core/runtime/sweep_runner.py, omnidriver/cli.py
    :fallback: legacy_environment_diagnostics, legacy_configured_environment, legacy_load_environment
    :status: optional
    """

    def diagnostics(
        self,
        workflow_dag: dict[str, Any] | None,
        *,
        env: dict[str, str] | None = None,
        explicit_bashrc: str | None = None,
        driver_context: Any | None = None,
    ) -> tuple[Any, ...]: ...

    def configure(
        self, env: dict[str, str], driver_context: Any | None,
    ) -> dict[str, str]: ...


class OverrideSchemaCapability(Protocol):
    """The plugin's authored configuration vocabulary.

    ``config_schema`` is the machine-readable description of the ``--config``
    JSON an agent writes, including a worked example for the named tutorial.
    ``dict_entry_catalog`` returns the plugin's dictionary entries arranged by
    its own document names, **unserialized** -- core owns serialization, the
    plugin owns the vocabulary and the document shape.

    :adapts: get_dict_entry_catalog, get_override_schema
    :consumed-by: omnidriver/core/introspection.py
    :fallback: none
    :status: mandatory
    """

    def config_schema(
        self, tutorial_name: str, make_spec_info: dict[str, Any],
    ) -> dict[str, Any]: ...
    def dict_entry_catalog(self) -> dict[str, Any]: ...


class RuntimeEvidenceCapability(Protocol):
    """Where the plugin's runtime evidence lives.

    Telemetry uses ``solve_step_commands`` and ``telemetry_source_globs``;
    provenance uses ``extra_provenance_paths``; observable extraction can use
    ``artifact_value_reader``. Plugins return empty declarations when a kind
    of runtime evidence does not apply.

    :adapts: get_artifact_value_reader, get_extra_provenance_paths, get_solve_step_commands, get_telemetry_source_globs
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: none
    :status: mandatory
    """

    def solve_step_commands(self) -> frozenset[str]: ...
    def telemetry_source_globs(self, command: str) -> tuple[str, ...]: ...
    def extra_provenance_paths(self, case_root: Path) -> tuple[RuntimeDependency, ...]: ...
    def artifact_value_reader(self, artifact_format: str) -> Any | None: ...


class CaseProvenanceCapability(Protocol):
    """Solver-declared case classification for the provenance snapshot.

    ``required_inputs`` returns already-*resolved* paths, not patterns --
    field names and locations are adapter-configurable, so a field's
    canonical path is not knowable from its name alone.
    ``generated_output_globs`` may stay globs: generated diagnostic outputs
    have fixed names.

    Both take the resolved case dictionaries (not just the model name) and
    the selected start time, because gating is by dictionary *value*: e.g.
    ``conductivitySource field`` vs ``uniform`` flips a mandatory read on
    and off, and an absent key silently defaults to ``uniform``.

    Routed through the capability adapter exactly like every other plugin
    capability -- deliberately **not** a mandatory ``SolverPlugin``
    member, so existing v2 third-party plugins keep loading. The adapter's
    fallback returns empty for both, which under the resolution precedence
    (a DAG step's ``consumes``, then a plugin's ``required_inputs``, then
    ``generated_output_globs``, then: unknown files are ``required_input``)
    means "everything unknown is a required input" -- the safe default for
    a plugin that declares nothing.

    :adapts: get_generated_output_globs, get_required_inputs
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: none
    :status: optional
    """

    def required_inputs(
        self,
        case_root: Path,
        resolved_case: dict[str, Any],
        selected_start_time: str,
    ) -> tuple[ResolvedInput, ...]: ...

    def generated_output_globs(
        self,
        case_root: Path,
        resolved_case: dict[str, Any],
        selected_start_time: str,
    ) -> tuple[str, ...]: ...


class ReportCatalogCapability(Protocol):
    """Post-run report definitions the active plugin wants offered.

    ``report_catalog`` (:mod:`omnidriver.core.report_catalog`) owns the
    solver-neutral machinery -- ``ReportDefinition``, the ``applicable_when``
    predicate evaluator, the JSON record shape -- but the *catalog itself*
    (which reports exist, e.g. "Vm field" or "activation map") is
    adapter-specific data. Not a mandatory ``SolverPlugin`` member, so
    existing v2 third-party plugins keep loading; the fallback
    (``legacy_report_catalog``) is empty until an adapter declares reports.

    :adapts: get_report_catalog
    :consumed-by: scripts/export-report-catalog.py
    :fallback: legacy_report_catalog
    :status: optional
    """

    def reports(self) -> tuple["ReportDefinition", ...]: ...


class NamedCatalogsCapability(Protocol):
    """The plugin's own named catalogs, namespaced generically.

    ``catalogs`` returns a mapping from plugin-chosen catalog name to
    plugin-chosen catalog content (e.g. the cardiac plugin's
    ``ionic_model_catalog``/``active_tension_catalog``) -- core imposes no
    key set, it only namespaces the whole mapping under
    ``describe_entry``'s ``plugin_catalogs`` key and serializes it. Not a
    mandatory ``SolverPlugin`` member, so existing v2 third-party plugins
    keep loading; the fallback (``legacy_named_catalogs``) is empty until an
    adapter declares its own catalogs.

    :adapts: get_named_catalogs
    :consumed-by: omnidriver/core/introspection.py
    :fallback: legacy_named_catalogs
    :status: optional
    """

    def catalogs(self) -> dict[str, Any]: ...


class OverrideScopeCapability(Protocol):
    """Plugin-declared ``$TOKEN.`` override scopes for the agent-facing
    ``step --strict --apply`` path.

    Generalizes adapter-defined scope tokens without assuming a particular
    token count or path. Not a mandatory ``SolverPlugin`` member, so existing
    v2 third-party plugins keep loading; the fallback
    (``legacy_override_scopes``) returns no scopes until an adapter declares
    them.

    :adapts: get_override_scopes, get_override_target_paths, apply_overrides, inspect_effective_configuration
    :consumed-by: omnidriver/openfoam/apply_overrides.py, omnidriver/core/runtime/provenance_inputs.py, omnidriver/core/runtime/step_candidate.py, omnidriver/core/strict_planning.py
    :fallback: legacy_override_scopes, legacy_override_target_paths, legacy_apply_overrides, legacy_inspect_effective_configuration
    :status: optional
    """

    def scopes(self) -> tuple[Any, ...]: ...

    def target_paths(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
    ) -> tuple[Path, ...]: ...

    def apply(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]: ...

    def inspect(
        self, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]: ...


class DictRegenerationCapability(Protocol):
    """Plugin-declared bare "selector" overrides that must REGENERATE a
    dict file rather than key-patch it, for the agent-facing
    ``step --strict --apply`` path.

    A sibling of :class:`OverrideScopeCapability`: that one covers
    ``$TOKEN.``-scoped leaves that patch in place; this one covers bare
    selectors (e.g. cardiacFoam's ``myocardiumSolver``) whose value change
    restructures the file -- renames a sub-block, changes which sibling
    keys are legal -- so a single key/value/scope patch cannot express it.
    Not a mandatory ``SolverPlugin`` member, so existing v2 third-party
    plugins keep loading; the fallback (``legacy_dict_regeneration_scopes``)
    declares the cardiac plugin's one scope and an empty tuple for everyone
    else, matching :class:`OverrideScopeCapability`.

    :adapts: get_regeneration_scopes
    :consumed-by: omnidriver/openfoam/apply_overrides.py
    :fallback: legacy_dict_regeneration_scopes
    :status: optional
    """

    def scopes(self) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class _TutorialCatalogAdapter:
    plugin: "SolverPlugin"

    def catalog(self) -> dict[str, Any]:
        return self.plugin.get_tutorial_catalog()

    def displays(self) -> tuple[Any, ...]:
        return self.plugin.get_tutorial_displays()


@dataclass(frozen=True)
class _DictionaryCatalogAdapter:
    plugin: "SolverPlugin"

    def entries(self) -> tuple[Any, ...]:
        return self.plugin.get_dict_entries()

    def catalog(self) -> Any:
        return self.plugin.get_dictionary_catalog()

    def groups(self) -> dict[str, tuple[Any, ...]]:
        return self.plugin.get_dict_groups()

    def phases(self) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_phases", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_phases

        return legacy_phases(self.plugin)


@dataclass(frozen=True)
class _CapabilityManifestAdapter:
    plugin: "SolverPlugin"

    def manifest(self) -> Any:
        return self.plugin.get_capabilities()


@dataclass(frozen=True)
class _ConfigurationValidatorAdapter:
    plugin: "SolverPlugin"

    def validate(
        self, request: ConfigurationValidationRequest,
    ) -> tuple["StrictDiagnostic", ...]:
        return self.plugin.validate_configuration(request.spec)


@dataclass(frozen=True)
class _RunSemanticValidatorAdapter:
    plugin: "SolverPlugin"

    def validate(self, request: RunSemanticValidationRequest) -> tuple[Any, ...]:
        return self.plugin.validate_run_semantics(request.context)


@dataclass(frozen=True)
class _ArtifactPredictorAdapter:
    plugin: "SolverPlugin"

    def predict(self, request: ArtifactPredictionRequest) -> tuple["DataArtifact", ...]:
        return self.plugin.predict_data_artifacts(request.case_root, request.spec)


@dataclass(frozen=True)
class _RunDocumentConfigurationAdapter:
    plugin: "SolverPlugin"

    def build(
        self, request: RunDocumentConfigurationRequest,
    ) -> tuple[dict[str, dict[str, Any]], tuple["StrictDiagnostic", ...]]:
        hook = getattr(self.plugin, "build_run_document_config", None)
        if callable(hook):
            return hook(request.spec)
        # Omitting this optional hook means there is no generated config.
        from .compatibility import legacy_run_document_config

        return legacy_run_document_config(self.plugin, request.spec)

    def schema(self) -> dict[str, Any]:
        return self.plugin.get_run_document_config_schema()


@dataclass(frozen=True)
class _CxxMappingAdapter:
    plugin: "SolverPlugin"

    def profile(self) -> Any:
        return self.plugin.get_profile()


@dataclass(frozen=True)
class _DictDiagnosticsAdapter:
    plugin: "SolverPlugin"

    def function_object_fields(
        self, case_root: Path, *, samplable: dict[str, Any],
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_function_object_field_diagnostics", None)
        if callable(hook):
            return tuple(hook(case_root, samplable=samplable))
        from .compatibility import legacy_function_object_field_diagnostics

        return tuple(legacy_function_object_field_diagnostics(case_root, samplable=samplable))

    def case_dict_keys(
        self,
        case_root: Path,
        *,
        catalogued_paths: Any,
        dict_relpaths: tuple[str, ...],
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_case_dict_key_diagnostics", None)
        if callable(hook):
            return tuple(hook(
                case_root, catalogued_paths=catalogued_paths, dict_relpaths=dict_relpaths,
            ))
        from .compatibility import legacy_case_dict_key_diagnostics

        return tuple(legacy_case_dict_key_diagnostics(
            case_root, catalogued_paths=catalogued_paths, dict_relpaths=dict_relpaths,
        ))


@dataclass(frozen=True)
class _MeshDiagnosticPolicyAdapter:
    plugin: "SolverPlugin"

    def is_nondimensional(self, spec: "TutorialSpec") -> bool:
        hook = getattr(self.plugin, "is_nondimensional_case", None)
        if callable(hook):
            return bool(hook(spec))
        from .compatibility import legacy_nondimensional_case

        return legacy_nondimensional_case(self.plugin, spec)

    def extra_geometry_diagnostics(self, case_root: Path) -> tuple[Any, ...]:
        """Return plugin-owned geometry diagnostics, or none when absent."""
        hook = getattr(self.plugin, "get_mesh_geometry_diagnostics", None)
        if callable(hook):
            return tuple(hook(case_root))
        return ()

    def base_geometry_diagnostics(self, case_root: Path) -> tuple[Any, ...]:
        """Return adapter-owned base-geometry diagnostics, if supported.

        Core does not parse a solver's mesh format directly. An absent hook
        yields the neutral compatibility result.
        """
        hook = getattr(self.plugin, "get_base_mesh_geometry_diagnostics", None)
        if callable(hook):
            return tuple(hook(case_root))
        from .compatibility import legacy_base_mesh_geometry_diagnostics

        return tuple(legacy_base_mesh_geometry_diagnostics(case_root))


@dataclass(frozen=True)
class _CaseCompatibilityAdapter:
    plugin: "SolverPlugin"

    def has_case_marker(self, request: CaseCompatibilityRequest) -> bool:
        hook = getattr(self.plugin, "has_case_marker", None)
        if callable(hook):
            return bool(hook(request.case_root))
        from .compatibility import legacy_case_marker

        return legacy_case_marker(self.plugin, request.case_root)

    def is_runnable_without_workflow(self, request: CaseCompatibilityRequest) -> bool:
        hook = getattr(self.plugin, "is_case_runnable_without_workflow", None)
        if callable(hook):
            return bool(hook(request.case_root))
        from .compatibility import legacy_case_runnable_without_workflow

        return legacy_case_runnable_without_workflow(self.plugin, request.case_root)


@dataclass(frozen=True)
class _SweepMaterializerAdapter:
    plugin: "SolverPlugin"

    def route(self, request: SweepRoutingRequest, *, driver_context: Any) -> dict[str, Any]:
        hook = getattr(self.plugin, "route_sweep_case_values", None)
        if callable(hook):
            return hook(
                base=request.base,
                resolved_axis_values=request.resolved_axis_values,
                driver_context=driver_context,
            )
        # Compatibility bridge for existing third-party-style plugins. A
        # missing adapter route remains a refusal rather than another
        # adapter's materializer.
        from .compatibility import legacy_route_sweep_case

        return legacy_route_sweep_case(
            self.plugin,
            base=request.base,
            resolved_axis_values=request.resolved_axis_values,
            driver_context=driver_context,
        )

    def materialize(self, request: SweepMaterializationRequest) -> None:
        hook = getattr(self.plugin, "materialize_sweep_case", None)
        if callable(hook):
            hook(case_dir=request.case_dir, routed=request.routed)
            return
        from .compatibility import legacy_materialize_sweep_case

        legacy_materialize_sweep_case(
            self.plugin, case_dir=request.case_dir, routed=request.routed
        )


@dataclass(frozen=True)
class _CommandAuthorizationAdapter:
    plugin: "SolverPlugin"

    def solver_commands(self) -> frozenset[str]:
        return frozenset(self.plugin.get_solver_commands())

    def auxiliary_commands(self) -> frozenset[str]:
        return frozenset(self.plugin.get_auxiliary_commands())

    def environment_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_environment_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import legacy_environment_commands

        return legacy_environment_commands(self.plugin)

    def is_installed_environment_command(self, command: str) -> bool:
        hook = getattr(self.plugin, "is_installed_environment_command", None)
        if callable(hook):
            return bool(hook(command))
        from .compatibility import legacy_is_installed_environment_command

        return legacy_is_installed_environment_command(self.plugin, command)

    def utility_manifests(self) -> dict[str, Any]:
        return dict(self.plugin.get_utility_manifests())

    def utility_roots(self) -> tuple[Path, ...]:
        return tuple(self.plugin.get_utility_roots())


@dataclass(frozen=True)
class _CaseIntrospectionAdapter:
    plugin: "SolverPlugin"

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        return dict(self.plugin.resolve_case_models(case_root))

    def samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        return {k: tuple(v) for k, v in self.plugin.get_samplable_fields(resolved).items()}

    def selected_start_time(
        self, case_root: Path, resolved_case: dict[str, Any], *, driver_context: Any,
    ) -> str | None:
        hook = getattr(self.plugin, "get_selected_start_time", None)
        if callable(hook):
            result = hook(case_root, resolved_case)
            # A blank result is not "no opinion" -- ``case_root / "" ==
            # case_root``, so it would silently walk the entire case tree
            # instead of the intended time directory. Fail loudly, matching
            # this codebase's rule that an unclassified/malformed input is a
            # spurious refusal, never a silent misclassification.
            if not isinstance(result, str) or not result:
                raise TypeError(
                    f"{self.plugin.plugin_id}.get_selected_start_time() must return "
                    f"a non-empty string, got {result!r}"
                )
            return result
        return None


@dataclass(frozen=True)
class _CaseFileContractAdapter:
    plugin: "SolverPlugin"

    def _rules(self) -> tuple["CaseFileRule", ...]:
        return tuple(self.plugin.get_profile().case_files)

    def required_rules(self) -> tuple["CaseFileRule", ...]:
        """Required rules with their ``role`` intact, so a consumer need not
        re-derive plugin semantics from a path prefix."""
        return tuple(rule for rule in self._rules() if rule.required == "always")

    def required_files(self) -> tuple[str, ...]:
        return tuple(rule.path for rule in self.required_rules())

    def conditional_files(self) -> tuple[str, ...]:
        return tuple(rule.path for rule in self._rules() if rule.required != "always")

    def all_rules(self) -> tuple["CaseFileRule", ...]:
        return self._rules()

    def describe_config_resolution(self) -> str:
        hook = getattr(self.plugin, "get_config_resolution_description", None)
        if callable(hook):
            return str(hook())
        from .compatibility import legacy_describe_config_resolution

        return legacy_describe_config_resolution(self.plugin)

@dataclass(frozen=True)
class _CaseRuntimeConventionsAdapter:
    plugin: "SolverPlugin"

    def conventions(self) -> CaseRuntimeConventions:
        hook = getattr(self.plugin, "get_case_runtime_conventions", None)
        if callable(hook):
            result = hook()
            if not isinstance(result, CaseRuntimeConventions):
                raise TypeError(
                    f"{self.plugin.plugin_id}.get_case_runtime_conventions() must "
                    f"return CaseRuntimeConventions, got {result!r}"
                )
            return result
        from .compatibility import legacy_case_runtime_conventions

        return legacy_case_runtime_conventions()


@dataclass(frozen=True)
class _EnvironmentPreflightAdapter:
    plugin: "SolverPlugin"

    def diagnostics(
        self,
        workflow_dag: dict[str, Any] | None,
        *,
        env: dict[str, str] | None = None,
        explicit_bashrc: str | None = None,
        driver_context: Any | None = None,
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_environment_diagnostics", None)
        if callable(hook):
            return tuple(hook(
                workflow_dag, env=env, explicit_bashrc=explicit_bashrc,
                driver_context=driver_context,
            ))
        from .compatibility import legacy_environment_diagnostics

        return tuple(legacy_environment_diagnostics(
            workflow_dag, env=env, explicit_bashrc=explicit_bashrc,
            driver_context=driver_context,
        ))

    def configure(
        self, env: dict[str, str], driver_context: Any | None,
    ) -> dict[str, str]:
        hook = getattr(self.plugin, "get_configured_environment", None)
        if callable(hook):
            return dict(hook(env, driver_context))
        from .compatibility import legacy_configured_environment

        return dict(legacy_configured_environment(env, driver_context))

    def load(
        self, *, explicit_bashrc: Any | None, driver_context: Any | None,
    ) -> dict[str, str]:
        hook = getattr(self.plugin, "get_loaded_environment", None)
        if callable(hook):
            return dict(hook(explicit_bashrc=explicit_bashrc, driver_context=driver_context))
        from .compatibility import legacy_load_environment

        return dict(legacy_load_environment(
            explicit_bashrc=explicit_bashrc, driver_context=driver_context,
        ))


@dataclass(frozen=True)
class _OverrideSchemaAdapter:
    plugin: "SolverPlugin"

    def config_schema(
        self, tutorial_name: str, make_spec_info: dict[str, Any],
    ) -> dict[str, Any]:
        return dict(self.plugin.get_override_schema(tutorial_name, make_spec_info))

    def dict_entry_catalog(self) -> dict[str, Any]:
        return dict(self.plugin.get_dict_entry_catalog())


@dataclass(frozen=True)
class _RuntimeEvidenceAdapter:
    plugin: "SolverPlugin"

    def solve_step_commands(self) -> frozenset[str]:
        return frozenset(self.plugin.get_solve_step_commands())

    def telemetry_source_globs(self, command: str) -> tuple[str, ...]:
        return tuple(self.plugin.get_telemetry_source_globs(command))

    def extra_provenance_paths(self, case_root: Path) -> tuple[Path, ...]:
        return tuple(self.plugin.get_extra_provenance_paths(case_root))

    def artifact_value_reader(self, artifact_format: str):
        return self.plugin.get_artifact_value_reader(artifact_format)


@dataclass(frozen=True)
class _CaseProvenanceAdapter:
    plugin: "SolverPlugin"

    def required_inputs(
        self,
        case_root: Path,
        resolved_case: dict[str, Any],
        selected_start_time: str,
    ) -> tuple[ResolvedInput, ...]:
        hook = getattr(self.plugin, "get_required_inputs", None)
        if callable(hook):
            return tuple(hook(case_root, resolved_case, selected_start_time))
        return ()

    def generated_output_globs(
        self,
        case_root: Path,
        resolved_case: dict[str, Any],
        selected_start_time: str,
    ) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_generated_output_globs", None)
        if callable(hook):
            return tuple(hook(case_root, resolved_case, selected_start_time))
        return ()


@dataclass(frozen=True)
class _ReportCatalogAdapter:
    plugin: "SolverPlugin"

    def reports(self) -> tuple["ReportDefinition", ...]:
        hook = getattr(self.plugin, "get_report_catalog", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_report_catalog

        return legacy_report_catalog(self.plugin)


@dataclass(frozen=True)
class _NamedCatalogsAdapter:
    plugin: "SolverPlugin"

    def catalogs(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_named_catalogs", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import legacy_named_catalogs

        return legacy_named_catalogs(self.plugin)


@dataclass(frozen=True)
class _OverrideScopeAdapter:
    plugin: "SolverPlugin"

    def scopes(self) -> tuple["OverrideScope", ...]:
        hook = getattr(self.plugin, "get_override_scopes", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_override_scopes

        return legacy_override_scopes(self.plugin)

    def apply(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Apply adapter-owned overrides, or leave them unsupported.

        The context is passed so an adapter can resolve its own transaction
        and provenance requirements. Core does not delegate to a solver-
        specific mutator when the hook is absent.
        """
        hook = getattr(self.plugin, "apply_overrides", None)
        if callable(hook):
            hook(overrides, case_root=case_root)
            return ()
        from .compatibility import legacy_apply_overrides

        return legacy_apply_overrides(
            overrides, case_root=case_root, driver_context=driver_context,
            execution_env=execution_env,
        )

    def target_paths(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
    ) -> tuple[Path, ...]:
        hook = getattr(self.plugin, "get_override_target_paths", None)
        if callable(hook):
            return tuple(Path(path) for path in hook(overrides, case_root=case_root))
        if callable(getattr(self.plugin, "apply_overrides", None)):
            raise ValueError(
                f"plugin {self.plugin.plugin_id!r} implements apply_overrides() "
                "but does not declare get_override_target_paths(); crash-safe "
                "--apply is unavailable"
            )
        from .compatibility import legacy_override_target_paths

        return legacy_override_target_paths(
            overrides, case_root=case_root, driver_context=driver_context,
        )

    def inspect(
        self, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        hook = getattr(self.plugin, "inspect_effective_configuration", None)
        if callable(hook):
            return tuple(hook(case_root=case_root, execution_env=execution_env))
        from .compatibility import legacy_inspect_effective_configuration

        return legacy_inspect_effective_configuration(
            case_root=case_root,
            driver_context=driver_context,
            execution_env=execution_env,
        )


@dataclass(frozen=True)
class _DictRegenerationAdapter:
    plugin: "SolverPlugin"

    def scopes(self) -> tuple["RegenerationScope", ...]:
        hook = getattr(self.plugin, "get_regeneration_scopes", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_dict_regeneration_scopes

        return legacy_dict_regeneration_scopes(self.plugin)


@dataclass(frozen=True)
class PluginCapabilities:
    """Core's focused, internal view over one loaded plugin.

    **Direction matters.** This is not an authoring surface. A plugin author
    implements :class:`~omnidriver.core.plugin_interface.SolverPlugin`
    and optionally ``SolverPluginOptionalHooks``; this bundle is what *core*
    holds to consult that plugin, pointing the other way. Nothing here is
    implemented by a plugin.

    Its purpose is to stop core reaching through ``DriverContext.plugin``
    directly: each field is a narrow seam over one concern, so a core module
    can depend on the one capability it needs instead of the whole plugin.
    ``test_plugin_dependency_boundary.py`` enforces that -- no production
    module may use ``driver_context.plugin.``.

    **Reading a capability.** Every capability Protocol below carries prose
    explaining why the seam exists, then four structured fields:

    ``:adapts:``
        the plugin member(s) the adapter calls, or ``none``
    ``:consumed-by:``
        core modules that really touch this capability (subset, not exhaustive)
    ``:fallback:``
        the ``compatibility.py`` function used when the hook is absent
    ``:status:``
        ``mandatory`` (every adapted member is required by plugin validation),
        ``optional`` (every member is probed and degraded), or ``mixed``
        (the capability combines both kinds)

    Those fields are the single source of the "Plugin capability seams" table
    in ``ARCHITECTURE.md``, rendered by
    ``scripts/export-capability-seams.py`` and kept honest by
    ``test_capability_seam_documentation.py`` -- which checks that every
    ``:adapts:`` names a real plugin member and every ``:fallback:`` a real
    compatibility function, so a stale reference fails rather than rots.

    A missing optional hook invokes its named fallback. Fallback behavior is
    independent of plugin identity. Sweep routing and materialization refuse
    when absent because they have no neutral result.
    """

    tutorials: TutorialCatalogCapability
    dictionaries: DictionaryCatalogCapability
    manifest: CapabilityManifestCapability
    configuration_validator: ConfigurationValidatorCapability
    run_semantic_validator: RunSemanticValidatorCapability
    artifacts: ArtifactPredictorCapability
    run_document_configuration: RunDocumentConfigurationCapability
    cxx_mapping: CxxMappingCapability
    mesh_diagnostic_policy: MeshDiagnosticPolicyCapability
    case_compatibility: CaseCompatibilityCapability
    sweep_materializer: SweepMaterializerCapability
    command_authorization: CommandAuthorizationCapability
    case_introspection: CaseIntrospectionCapability
    case_files: CaseFileContractCapability
    case_runtime_conventions: CaseRuntimeConventionsCapability
    environment_preflight: EnvironmentPreflightCapability
    dict_diagnostics: DictDiagnosticsCapability
    override_schema: OverrideSchemaCapability
    runtime_evidence: RuntimeEvidenceCapability
    case_provenance: CaseProvenanceCapability
    report_catalog: ReportCatalogCapability
    named_catalogs: NamedCatalogsCapability
    override_scopes: OverrideScopeCapability
    dict_regeneration: DictRegenerationCapability


def adapt_plugin_capabilities(plugin: "SolverPlugin") -> PluginCapabilities:
    """Wrap one loaded plugin in the capability bundle core consumes.

    Called once per :class:`~omnidriver.core.plugin_interface.DriverContext`
    and cheap: every adapter is a frozen dataclass holding the plugin, and no
    plugin member is called here. Optional hooks are probed lazily at each
    call site, so a plugin missing one is adapted successfully and degrades
    only when that capability is actually used.
    """

    return PluginCapabilities(
        tutorials=_TutorialCatalogAdapter(plugin),
        dictionaries=_DictionaryCatalogAdapter(plugin),
        manifest=_CapabilityManifestAdapter(plugin),
        configuration_validator=_ConfigurationValidatorAdapter(plugin),
        run_semantic_validator=_RunSemanticValidatorAdapter(plugin),
        artifacts=_ArtifactPredictorAdapter(plugin),
        run_document_configuration=_RunDocumentConfigurationAdapter(plugin),
        cxx_mapping=_CxxMappingAdapter(plugin),
        mesh_diagnostic_policy=_MeshDiagnosticPolicyAdapter(plugin),
        case_compatibility=_CaseCompatibilityAdapter(plugin),
        sweep_materializer=_SweepMaterializerAdapter(plugin),
        command_authorization=_CommandAuthorizationAdapter(plugin),
        case_introspection=_CaseIntrospectionAdapter(plugin),
        case_files=_CaseFileContractAdapter(plugin),
        case_runtime_conventions=_CaseRuntimeConventionsAdapter(plugin),
        environment_preflight=_EnvironmentPreflightAdapter(plugin),
        dict_diagnostics=_DictDiagnosticsAdapter(plugin),
        override_schema=_OverrideSchemaAdapter(plugin),
        runtime_evidence=_RuntimeEvidenceAdapter(plugin),
        case_provenance=_CaseProvenanceAdapter(plugin),
        report_catalog=_ReportCatalogAdapter(plugin),
        named_catalogs=_NamedCatalogsAdapter(plugin),
        override_scopes=_OverrideScopeAdapter(plugin),
        dict_regeneration=_DictRegenerationAdapter(plugin),
    )
