"""Internal, focused capability seams for solver plugins.

The public :class:`SolverPlugin` protocol remains the compatibility contract for
Plan 1.  Core code consumes this bundle instead of reaching through
``DriverContext.plugin`` directly.  The adapters deliberately preserve the
legacy method calls, return values, call order, and exception behaviour.

Optional case-compatibility and sweep hooks let a plugin take ownership of
solver-specific behaviour without adding new required members to the public
protocol.  Plugins that do not provide those hooks retain the historical
omnidriver fallbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_interface import SolverPlugin
    from .plugin_profile import CaseFileRule
    from .quantities.model import ArtifactValueReader
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
    metadata ``describe`` renders. ``catalog`` is required: a plugin that
    registers no tutorials returns empty rather than omitting it. ``displays``
    is optional-neutral since 2026-09-26 (spec A3); absent, it answers ``()``,
    and core has no runtime consumer of it.

    :adapts: get_tutorial_catalog, get_tutorial_displays
    :consumed-by: omnidriver/core/runtime/registry.py, omnidriver/cardiacfoam/dict_builder.py
    :fallback: none
    :status: get_tutorial_catalog=required, get_tutorial_displays=optional-neutral
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

    All three are optional-neutral since 2026-09-26 (spec A3). A plugin
    without dictionaries (openCARP, the toy) omits them, and each answers
    empty: ``()``, ``DictionaryCatalog({})``, ``{}``. Corrected that day: they
    were required, so every plugin had to stub them. This is the seam that
    keeps dictionary *syntax* knowledge (core's) apart from dictionary
    *meaning* (the plugin's).

    :adapts: get_dict_entries, get_dict_groups, get_dictionary_catalog, get_phases
    :consumed-by: omnidriver/dict_entries.py, omnidriver/cardiacfoam/dict_entries.py, omnidriver/cardiacfoam/sweep.py, omnidriver/openfoam/apply_overrides.py, omnidriver/openfoam/dict_builder.py, omnidriver/core/specs/validation.py, omnidriver/core/strict_planning.py
    :fallback: legacy_phases
    :status: optional-neutral
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
    :consumed-by: omnidriver/cardiacfoam/dict_entries.py, omnidriver/core/introspection.py, omnidriver/core/strict_planning.py
    :fallback: none
    :status: required
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
    :status: required
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
    :status: required
    """

    def validate(
        self, request: RunSemanticValidationRequest,
    ) -> tuple["StrictDiagnostic", ...]: ...


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
    :status: required
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
    :fallback: legacy_run_document_config, legacy_run_document_config_schema
    :status: optional-neutral
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
    :status: required
    """

    def profile(self) -> Any: ...


class DictDiagnosticsCapability(Protocol):
    """Warn-only checks of a case's on-disk dict files against declared
    vocabulary: sampled fields absent from the capability manifest, and dict
    keys absent from the plugin's catalogue.

    Both read and parse the case's dictionary files (via ``foamlib`` for
    OpenFOAM), which core has no business doing itself -- a FEniCS plugin's
    catalogue is checked against its own config format, not OpenFOAM syntax.
    Neither ever fails a plan; a false positive here is a question for a
    human, not a defect -- which is why they land in ``all_diagnostics`` but
    never in ``plan_diagnostics``. ``strict_planning.py``'s ``all_diagnostics``
    assembly carries the reasoning. (This used to cite
    ``strict_planning._resolve_entry``, which has never existed; the only
    ``resolve_entry`` in the repo is ``core/runtime/registry.py``'s, and it is
    not what the sentence meant.)

    :adapts: get_function_object_field_diagnostics, get_case_dict_key_diagnostics
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: legacy_function_object_field_diagnostics, legacy_case_dict_key_diagnostics
    :status: optional-neutral
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
    :status: optional-neutral
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

    ``is_case`` composes the THIRD filesystem question a caller used to ask
    by hand: ``registry._is_case_directory`` was
    ``has_case_marker(...) or _has_entrypoint(...)``, duplicated at every
    discovery call site. This collapses that into one predicate and adds a
    signal discovery never checked -- a case whose declared entrypoint was
    since removed, but which still carries a generated marker from a prior
    run (e.g. OpenFOAM's ``run_document.json``), is still this plugin's case.
    Not a new plugin hook: it reads the already-adapted ``has_case_marker``
    plus whatever ``get_case_runtime_conventions`` the stack composes (an
    absent hook degrades through that capability's own neutral fallback, so
    ``is_case`` needs none of its own). (Task 10, 2026-09-22.)

    :adapts: has_case_marker, is_case_runnable_without_workflow
    :consumed-by: omnidriver/core/runtime/registry.py
    :fallback: legacy_case_marker, legacy_case_runnable_without_workflow
    :status: optional-neutral
    """

    def has_case_marker(self, request: CaseCompatibilityRequest) -> bool: ...
    def is_runnable_without_workflow(self, request: CaseCompatibilityRequest) -> bool: ...
    def is_case(self, request: CaseCompatibilityRequest) -> bool: ...


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
    :status: optional-refusing
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
    :fallback: legacy_auxiliary_commands, legacy_environment_commands, legacy_is_installed_environment_command, legacy_solver_commands, legacy_utility_manifests, legacy_utility_roots
    :status: optional-neutral
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
    :fallback: legacy_resolve_case_models, legacy_samplable_fields
    :status: optional-neutral
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

    ``get_profile`` deliberately backs this capability AND
    ``CxxMappingCapability``: one declaration, two consumers with different
    concerns. Recorded 2026-09-20 because it reads as a duplicate intake and
    is not one.

    :adapts: get_profile, get_config_resolution_description
    :consumed-by: omnidriver/core/runtime/strict_audit.py, omnidriver/core/tutorial_contracts.py, omnidriver/core/runtime/provenance_inputs.py
    :fallback: legacy_describe_config_resolution
    :status: get_profile=required, get_config_resolution_description=optional-neutral
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
    plugin without the optional hook receives only core's own run records
    (``runtime_records.CORE_RUNTIME_RECORDS``, merged into every answer since
    2026-09-26, spec A5): Core preserves every authored path and does not
    collect a convention-specific tree.

    :adapts: get_case_runtime_conventions
    :consumed-by: omnidriver/core/runtime/registry.py, omnidriver/core/runtime/sweep_runner.py
    :fallback: legacy_case_runtime_conventions
    :status: optional-neutral
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

    ``diagnostics`` and ``load`` both take an explicit path to an
    environment-sourcing script, and both now spell it ``explicit_bashrc`` --
    ``diagnostics`` used to spell it ``openfoam_bashrc``, naming OpenFOAM
    specifically for a parameter every environment needs (future/
    ENVIRONMENT_CONTRACT.md §10, Tier 3). The CLI flag threading it in is
    ``--environment-bashrc``. ``--openfoam-bashrc`` was shipped as a deprecated
    alias and then removed outright the same day, pre-publication -- this
    sentence used to claim the alias still worked, which ``cli.py`` and
    ``test_openfoam_bashrc_kwarg_is_no_longer_accepted`` both disprove.

    :adapts: get_environment_diagnostics, get_configured_environment, get_loaded_environment
    :consumed-by: omnidriver/core/strict_planning.py, omnidriver/core/runtime/sweep_runner.py, omnidriver/cli.py, omnidriver/conformance/checks.py
    :fallback: legacy_environment_diagnostics, legacy_configured_environment, legacy_load_environment
    :status: optional-neutral
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
    JSON an agent writes, including a worked example for the named tutorial,
    when the plugin has one to give. When it does not (an unrecognized
    tutorial, or no hook at all), the adapter derives the answer from
    :class:`RunDocumentConfigurationCapability`'s validated schema instead of
    handing back a second, independently-authored empty answer -- see
    :meth:`_OverrideSchemaAdapter.config_schema`. ``dict_entry_catalog``
    returns the plugin's dictionary entries arranged by its own document
    names, **unserialized** -- core owns serialization, the plugin owns the
    vocabulary and the document shape.

    :adapts: get_dict_entry_catalog, get_override_schema
    :consumed-by: omnidriver/core/introspection.py
    :fallback: legacy_dict_entry_catalog, legacy_override_schema
    :status: optional-neutral
    """

    def config_schema(
        self, tutorial_name: str, make_spec_info: dict[str, Any],
    ) -> dict[str, Any]: ...
    def dict_entry_catalog(self) -> dict[str, Any]: ...


class RuntimeEvidenceCapability(Protocol):
    """Where the plugin's runtime evidence lives.

    ``artifact_value_reader(format)`` returns the reader for one artifact
    format (``core.quantities.ArtifactValueReader``) or ``None``. A ``None``
    makes that artifact's quantities ``not_evaluated`` with the format
    named, never an implicit pass. Corrected 2026-09-26 (results as
    quantities): it was declaration-only.

    Telemetry collection consumes ``solve_step_commands`` and
    ``telemetry_source_globs``. Phase 2 (provenance) now consumes
    ``extra_provenance_paths`` for real.

    Every member degrades to empty for a plugin that declares nothing, which
    is the honest answer rather than a solver-shaped guess -- so this
    capability needs no compatibility fallback.

    :adapts: get_artifact_value_reader, get_extra_provenance_paths, get_log_redaction_patterns, get_solve_step_commands, get_telemetry_source_globs
    :consumed-by: omnidriver/conformance/checks.py, omnidriver/core/runtime/provenance_inputs.py, omnidriver/core/runtime/workflow_runner.py
    :fallback: none
    :status: optional-neutral
    """

    def solve_step_commands(self) -> frozenset[str]: ...
    def telemetry_source_globs(self, command: str) -> tuple[str, ...]: ...
    def extra_provenance_paths(self, case_root: Path) -> tuple[RuntimeDependency, ...]: ...
    def artifact_value_reader(self, artifact_format: str) -> "ArtifactValueReader | None": ...
    def log_redaction_patterns(self) -> frozenset[str]:
        """Patterns whose every match is replaced whole by ``[REDACTED]`` in a
        kept step log (``workflow_runner.redact_step_logs``); capture groups
        are not kept (wave-2 review I3, 2026-09-25)."""
        ...


class RecordSurfaceCapability(Protocol):
    """What an agent may address in a record, and what it should read first.

    Owner decision 2026-09-25 (spec 2026-09-25 §4, C10): discovering a
    record's keys and guidance must not depend on knowing which solver is
    underneath. ``key_catalog`` lists the keys a study may name for a case;
    ``guidance`` is solver-level advice for agents. Both degrade to empty,
    which C10 then reports as a failure for a real target.

    :adapts: get_agent_guidance, get_record_key_catalog
    :consumed-by: omnidriver/core/runtime/record_surface.py
    :fallback: none
    :status: optional-neutral
    """

    def key_catalog(self, case_root: Path) -> tuple[Mapping[str, Any], ...]: ...
    def guidance(self) -> tuple[Mapping[str, str], ...]: ...


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
    :status: optional-neutral
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
    :status: optional-neutral
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
    :status: optional-neutral
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
    :status: get_override_scopes=optional-neutral, get_override_target_paths=optional-refusing, apply_overrides=optional-refusing, inspect_effective_configuration=optional-neutral
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
    declares no regeneration scopes for any plugin, matching
    :class:`OverrideScopeCapability`. **Corrected 2026-09-20:** this used to
    say the fallback "declares the cardiac plugin's one scope and an empty
    tuple for everyone else" -- reading ``compatibility.py`` during the Phase
    0 tier retag (Task 1) found no such branch; the function returns ``()``
    unconditionally, with no ``plugin_id`` check, consistent with Phase 2
    Task 7 having deleted the identity-branching fallbacks elsewhere in this
    module.

    :adapts: get_regeneration_scopes
    :consumed-by: omnidriver/openfoam/apply_overrides.py
    :fallback: legacy_dict_regeneration_scopes
    :status: optional-neutral
    """

    def scopes(self) -> tuple[Any, ...]: ...


class ConfigValueCapability(Protocol):
    """Read one configuration value from an adapter's own file format.

    Before 2026-09-20 ``plugin_interface.py`` declared ``get_config_value_reader``
    under a heading naming this Protocol, but no module defined it -- so
    ``OpenFOAMEnvironmentPlugin`` and ``CardiacFoamPlugin`` each implemented
    the hook and returned a different callable, while core read neither: the
    only caller was ``CardiacFoamPlugin.get_selected_start_time`` invoking it
    on ``self``. Phase 1's composed provider seam needs a real reader here,
    so the hook is wired up rather than deleted. Not a mandatory
    ``SolverPlugin`` member, so existing v2 third-party plugins keep loading;
    a plugin that declares nothing has no adapter-specific format to read,
    which is the honest answer rather than a solver-shaped guess -- so this
    capability needs no compatibility fallback.

    :adapts: get_config_value_reader
    :consumed-by: omnidriver/cardiacfoam/run_document_config.py, omnidriver/core/runtime/record_execution.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def reader(self): ...


class DictKeyScannerCapability(Protocol):
    """Scan an adapter's C++ source for dictionary-key reads.

    ``_catalog_diagnostics`` (``strict_planning.py``) compares a solver
    plugin's catalogue against what its C++ actually reads, and until this
    capability existed it called ``compatibility.legacy_dict_key_scanner``
    directly, at module scope, unconditionally -- a "fallback" no adapter
    could ever override, since nothing probed for a real one first. The scan
    itself is C++/dictionary-format knowledge, not solver knowledge (the
    regex over ``.lookup("key")``-shaped call sites in ``dict_keys_scanner.py``
    knows nothing about ionic models or myocardium selectors), so it belongs
    to the OpenFOAM environment adapter, not to a specific solver plugin. Not
    a mandatory ``SolverPlugin`` member, so existing v2 third-party plugins
    keep loading; the fallback (``legacy_dict_key_scanner``) reports an empty
    drift -- no unmatched reads, no stale paths -- until an adapter declares a
    real scanner.

    :adapts: get_dict_key_scanner
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: legacy_dict_key_scanner
    :status: optional-neutral
    """

    def scan(
        self, source_root: Any, *, allowlist_path: Any, entries: Any,
    ) -> Any: ...


class TutorialRecordCapability(Protocol):
    """The tutorial records this plugin registers -- data, not factories.

    A record (``core.tutorial_records.TutorialRecord``) names a native case
    path relative to the environment's own cases root, the axis names it
    allows, and its workflow steps. Distinct from ``TutorialCatalogCapability
    .catalog()``'s ``spec_factories``, which builds a ``TutorialSpec`` by
    calling plugin code: resolving a record calls no plugin code at all,
    until an axis it names actually runs (design doc
    ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
    §3). ``runtime.registry.resolve_entry`` dispatches on this catalog
    explicitly, alongside the factory registry and a bare case path -- never
    trying one and falling back to another.

    **No fallback (review finding M1).** ``catalog()`` returns ``None``, not
    ``{}``, when the plugin declares no ``get_tutorial_records`` hook at all
    -- distinct from a plugin that implements the hook and simply registers
    no records yet. ``runtime.registry.resolve_entry`` treats ``None`` as
    "this stack dispatches no tutorial records", skipping record dispatch
    explicitly rather than iterating a fabricated empty mapping.

    :adapts: get_tutorial_records
    :consumed-by: omnidriver/core/runtime/registry.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def catalog(self) -> dict[str, Any] | None: ...


class AxisCapability(Protocol):
    """The named axes this plugin provides for a tutorial-record study.

    An axis (``core.tutorial_records.AxisContract``) is a name, the value
    kind it accepts, and a pure function ``(value, staged_case_root) ->
    AxisResult`` deriving patches and workflow-step command arguments. Core
    defines the contract and ships none itself (design doc §3: "Core defines
    the contract and ships no solver axes") -- a bare study name not found in
    a record's ``allowed_axes`` *and* in this catalog is refused by
    ``tutorial_records.sort_study_name`` before anything runs.

    **No fallback (review finding M1).** ``catalog()`` returns ``None`` when
    the plugin declares no ``get_axis_catalog`` hook -- callers (currently
    only ``record_execution._resolve_and_split``) treat that the same as an
    empty catalog: no fallback need branch on it, since a bare study name
    refuses identically either way.

    :adapts: get_axis_catalog
    :consumed-by: omnidriver/core/runtime/record_execution.py
    :fallback: none
    :status: optional-neutral
    """

    def catalog(self) -> dict[str, Any] | None: ...


class RecordKeyValidationCapability(Protocol):
    """Whether a tutorial-record study's direct ``document:key`` name is one
    this adapter's own catalog recognises, and what value shape it declares.

    Tutorial-record studies name a document key literally
    (``document:dotted.path``); core sorts that shape out
    (``tutorial_records.sort_study_name``) but owns no vocabulary of its own
    to say whether, e.g., ``constant/someProperties:someModel`` is a real key
    an adapter's own source reads, or what Python shape its value must have
    -- that is a solver-specific key catalog's job, one per plugin.

    ``validator()`` returns a ``(document, key_path, value) -> (value_kind,
    validated)`` callable, or ``None`` when the plugin declares no
    ``get_record_key_validator`` hook. Called, that callable returns
    ``(value_kind, validated)`` for a name the catalog recognises, or raises
    for one it does not -- refusing an undeclared key outright (design §5: "a
    [solver]-owned key absent from the catalog... never bypassed") is the
    adapter's own choice. An adapter that instead accepts an undeclared key
    unchecked (the environment-owned-key exception -- a key some underlying
    format reads but this plugin has no full catalog for yet) returns
    ``(inferred_kind, False)`` rather than raising; core does not choose
    between those two answers, and takes no closed list of "validated
    document prefixes" of its own.

    **No fallback (review finding M1).** A stack with no validator has no
    catalog to check ANY direct key -- or, since ``resolve_case_patches`` now
    validates axis-produced patches too (M3), any axis output -- against.
    ``record_execution._resolve_and_split`` reads ``validator() is None`` and
    REFUSES BY NAME before running a record case at all, rather than letting
    every key silently through unchecked the way ``legacy_record_key
    _validation`` used to (by raising only once a direct key was actually
    looked up, which an axis-only study could dodge entirely).

    :adapts: get_record_key_validator
    :consumed-by: omnidriver/core/runtime/record_execution.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def validator(self) -> Any | None: ...


class CaseValueComparisonCapability(Protocol):
    """Whether a proposed patch value already matches the case's current one.

    A tutorial-record patch equal to the staged case's current value is
    reported ``unchanged`` and not written (design §4 step 7). Never Python
    ``==``/string equality: an adapter's own typed comparison exists
    precisely because a requested ``1e-3`` and a case's resolved ``0.001``
    can be the same underlying value while being unequal Python strings.
    This capability delegates that typed judgement entirely to the adapter;
    core only calls it.

    ``comparator()`` returns a ``(value_kind, requested, current) -> bool``
    callable, or ``None`` when the adapter offers no such comparison.
    ``tutorial_records.split_unchanged``, called directly, still treats
    ``None`` as "cannot determine" and reports everything changed -- but
    ``record_execution._resolve_and_split`` (review finding M1/M4) reads
    ``comparator() is None`` first and REFUSES BY NAME before running a
    record case at all: a stack that cannot tell "unchanged" from "changed"
    must not silently report every no-op as a change and commit it, which is
    what happened before this capability had no fallback of its own
    (``legacy_case_value_comparator`` quietly returned ``None`` from a plugin
    that never declared an opinion either way, and nothing upstream refused).

    **No fallback (review finding M1).**

    :adapts: get_case_value_comparator
    :consumed-by: omnidriver/core/runtime/record_execution.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def comparator(self) -> Any: ...


class CaseWriterCapability(Protocol):
    """How a framework-authored case mutation becomes reviewable bytes.

    Three answers from up to three owners. ``resolve`` is the selected
    adapter's and is pure. ``render`` belongs to whichever provider declares
    the file's format, one declarer per format. Committing is core's and is not
    here at all -- see :mod:`omnidriver.core.case_transaction`.

    The fallback cannot be neutral. An empty resolution silently yields a case
    that is not the one requested, so an adapter without these hooks is refused
    by name.

    **Corrected 2026-09-23 (R2 finding 0):** ``get_supported_mutation_modes``
    used to say ``optional-neutral`` here, with a fallback of "every mode the
    adapter's ``resolve_case_mutation`` accepts". That default is exactly the
    root cause: three installed providers, implementing no
    ``resolve_case_mutation`` hook either, ended up reporting support for
    every mode while implementing none of them. The real behaviour is
    conditional and, once resolved, refusing rather than neutral: absent
    alongside a resolver -> raise, naming the provider (its supported modes
    are undeclared); absent alongside no resolver -> ``frozenset()``, which
    changes nothing because ``resolve()`` already refuses a hook-less
    provider by name before the mode check is ever reached. See
    ``_CaseWriterAdapter.supported_modes`` for the three-state logic.

    **Corrected 2026-09-23 (R2 finding 11):** ``get_rendered_formats`` said
    ``optional-neutral`` here too, alongside ``:fallback: none`` and the
    opening paragraph's own claim that "the fallback cannot be neutral" --
    two of four members contradicted the paragraph directly above them. Its
    OWN fallback, when the hook is absent, does return a neutral value
    (``frozenset()``) -- but that empty set then reaches ``renderer_for``,
    which refuses BY NAME the moment any format is looked up against it
    (nothing declares anything, so nothing is ever found). A hook whose
    absence is only neutral in isolation, and refuses on the very next step
    every real caller takes, is ``optional-refusing`` here, matching
    ``render_case_files`` and ``get_supported_mutation_modes``. All four
    members of this capability now refuse; none is neutral in practice, which
    is what the opening paragraph always claimed.

    No consumer yet (2026-09-22): the real one, ``case_transaction.py``'s
    ``commit_case_write``, is Phase 2 Task 5, a later batch in this plan.
    Update ``:consumed-by:`` to name it once that module lands and calls
    ``capabilities.case_writer``.

    :adapts: resolve_case_mutation, get_supported_mutation_modes, get_rendered_formats, render_case_files
    :consumed-by: none
    :fallback: none
    :status: resolve_case_mutation=optional-refusing, get_supported_mutation_modes=optional-refusing, get_rendered_formats=optional-refusing, render_case_files=optional-refusing
    """

    def resolve(self, request: Any, *, driver_context: Any) -> Any: ...
    def supported_modes(self) -> "frozenset[str]": ...
    def renderer_for(self, file_format: str) -> str: ...
    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class _TutorialCatalogAdapter:
    plugin: "SolverPlugin"

    def catalog(self) -> dict[str, Any]:
        return self.plugin.get_tutorial_catalog()

    def displays(self) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_tutorial_displays", None)
        return tuple(hook()) if callable(hook) else ()


@dataclass(frozen=True)
class _DictionaryCatalogAdapter:
    plugin: "SolverPlugin"

    def entries(self) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_dict_entries", None)
        return tuple(hook()) if callable(hook) else ()

    def catalog(self) -> Any:
        hook = getattr(self.plugin, "get_dictionary_catalog", None)
        if callable(hook):
            return hook()
        from .contracts.dictionary_catalog import DictionaryCatalog

        return DictionaryCatalog({})

    def groups(self) -> dict[str, tuple[Any, ...]]:
        hook = getattr(self.plugin, "get_dict_groups", None)
        return dict(hook()) if callable(hook) else {}

    def phases(self) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_phases", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_phases

        return legacy_phases(self.plugin)


@dataclass(frozen=True)
class _CapabilityManifestAdapter:
    """Assembles the accept-surface manifest from capabilities core already
    holds, merging in only what a plugin alone can supply.

    Before Task 10 (2026-09-22), ``manifest()`` was just
    ``self.plugin.get_capabilities()`` -- the WHOLE manifest, including the
    ``allowed_commands``/``samplable_fields`` sections, built and handed back
    BY the plugin. Since ``get_capabilities`` is a ``single``-shape composed
    member (:mod:`provider_stack`), that round trip meant only the
    most-specific provider's own self-authored answer ever won, discarding
    e.g. a companion environment provider's ``environment_commands``
    entirely -- exactly the isolation a composed stack (Tasks 6-9) exists to
    remove. Core now builds those two sections itself from the SAME
    ``command_authorization``/``case_introspection``/
    ``case_runtime_conventions`` reads every other capability here already
    uses, and merges in only what a plugin's own ``get_capabilities()``
    supplies that core cannot compose: a domain catalogue, such as
    cardiacFoam's ionic-model table.

    **No cache.** Phase 0 Task 12 made this a ``cached_property`` to avoid
    recomputing an expensive, plugin-authored manifest. Combined with
    ``DriverContext.capabilities`` also being cached, every ``.manifest()``
    caller sharing one ``DriverContext`` ended up sharing the exact same
    assembled dict -- including its ``ionic_models`` sub-dict -- for as long
    as that context lived (three call sites read it per context:
    ``dict_entries``, ``strict_planning``, ``introspection``). Nothing
    mutates it today, but that narrows the very isolation ``DriverContext``
    exists to provide (found by the Phase 0 review, 2026-09-20). Now that
    assembly is a handful of cheap composed-capability reads plus a small,
    already-copied domain dict, recomputing it on every call costs nothing,
    so the cache bought nothing but that narrowing -- it is removed here.
    **Corrected 2026-09-22:**
    ``test_capability_calls_are_cheap.py::test_capability_manifest_adapter_caches_per_instance``
    used to assert identity across two calls on one adapter; it now asserts
    the opposite, since there is no longer a cached object to share.
    """

    plugin: "SolverPlugin"

    def manifest(self) -> Any:
        from .capability_manifest import build_capability_manifest

        command_authorization = _CommandAuthorizationAdapter(self.plugin)
        case_introspection = _CaseIntrospectionAdapter(self.plugin)
        conventions = _CaseRuntimeConventionsAdapter(self.plugin).conventions()
        built = build_capability_manifest(
            environment_commands=command_authorization.environment_commands(),
            # The manifest advertises the accept-surface, so it lists both
            # kinds of authorized plugin command -- the solver/auxiliary
            # split only governs who may be credited with a run's artifacts.
            plugin_commands=(
                command_authorization.solver_commands()
                | command_authorization.auxiliary_commands()
            ),
            utility_manifests=command_authorization.utility_manifests(),
            # No case_root is available at this call site -- matches every
            # historical caller of get_capabilities(), which never resolved
            # one either -- so this resolves to the fixed solver fields only.
            samplable_fields=case_introspection.samplable_fields({}),
            case_script_commands=(
                frozenset(conventions.case_script_commands)
                | frozenset(conventions.case_entrypoints)
            ),
        )
        extra = self.plugin.get_capabilities()
        if extra:
            built.update(extra)
        return built


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

    def validate(
        self, request: RunSemanticValidationRequest,
    ) -> tuple["StrictDiagnostic", ...]:
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
        # Older plugins receive the neutral compatibility configuration.
        from .compatibility import legacy_run_document_config

        return legacy_run_document_config(self.plugin, request.spec)

    def schema(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_run_document_config_schema", None)
        if callable(hook):
            return hook()
        from .compatibility import legacy_run_document_config_schema

        return legacy_run_document_config_schema(self.plugin)


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
        """Plugin-owned plan-time geometry checks core cannot express.

        Core may provide generic geometry checks; an adapter may own further
        domain-specific point sets that are not mesh regions. A plugin that
        declares no such check contributes nothing -- there is no legacy
        fallback here, because "no extra checks" is the correct answer for a
        plugin that never had any.
        """
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

    def is_case(self, request: CaseCompatibilityRequest) -> bool:
        """Marker, entrypoint, or a leftover generated-case marker -- any one
        signal is enough. See the capability docstring for why this
        collapses ``registry``'s own duplicated ``has_case_marker(...) or
        _has_entrypoint(...)`` check."""
        if self.has_case_marker(request):
            return True
        hook = getattr(self.plugin, "get_case_runtime_conventions", None)
        if callable(hook):
            conventions = hook()
        else:
            from .compatibility import legacy_case_runtime_conventions

            conventions = legacy_case_runtime_conventions()
        case_root = request.case_root
        if any((case_root / relpath).is_file() for relpath in conventions.case_entrypoints):
            return True
        return any(
            (case_root / marker).exists() for marker in conventions.generated_case_markers
        )


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

    def materialize(
        self,
        request: SweepMaterializationRequest | None = None,
        *,
        case_dir: Path | None = None,
        routed: dict[str, Any] | None = None,
    ) -> None:
        """Write one resolved sweep case, or refuse by name.

        **Widened 2026-09-20 (Phase 1 Task 6).** Accepts the contract member's
        own argument names (``case_dir``/``routed``) as well as the request
        object. A composed stack is addressed in *member* terms -- that is what
        ``provider_stack`` composes -- and ``test_provider_composition_rules``
        calls this member's composed form that way. This is not a fallback: the
        two shapes name the same two values, and the request is still what the
        body works with.
        """
        if request is None:
            request = SweepMaterializationRequest(case_dir=case_dir, routed=routed)
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
        hook = getattr(self.plugin, "get_solver_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import legacy_solver_commands

        return legacy_solver_commands(self.plugin)

    def auxiliary_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_auxiliary_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import legacy_auxiliary_commands

        return legacy_auxiliary_commands(self.plugin)

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
        hook = getattr(self.plugin, "get_utility_manifests", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import legacy_utility_manifests

        return legacy_utility_manifests(self.plugin)

    def utility_roots(self) -> tuple[Path, ...]:
        hook = getattr(self.plugin, "get_utility_roots", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_utility_roots

        return legacy_utility_roots(self.plugin)


@dataclass(frozen=True)
class _CaseIntrospectionAdapter:
    plugin: "SolverPlugin"

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        hook = getattr(self.plugin, "resolve_case_models", None)
        if callable(hook):
            return dict(hook(case_root))
        from .compatibility import legacy_resolve_case_models

        return legacy_resolve_case_models(self.plugin, case_root)

    def samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        hook = getattr(self.plugin, "get_samplable_fields", None)
        if callable(hook):
            return {k: tuple(v) for k, v in hook(resolved).items()}
        from .compatibility import legacy_samplable_fields

        return legacy_samplable_fields(self.plugin, resolved)

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
        """The stack's declared generated paths, plus core's own run records
        (``runtime_records.CORE_RUNTIME_RECORDS``), whatever the plugin
        declares. Corrected 2026-09-26 (spec 2026-09-26 A5): a plugin
        without the hook used to receive an empty declaration, so staging a
        case a run had written carried core's own state into the next stage."""
        from .runtime_records import with_core_runtime_records

        hook = getattr(self.plugin, "get_case_runtime_conventions", None)
        if callable(hook):
            result = hook()
            if not isinstance(result, CaseRuntimeConventions):
                raise TypeError(
                    f"{self.plugin.plugin_id}.get_case_runtime_conventions() must "
                    f"return CaseRuntimeConventions, got {result!r}"
                )
            return with_core_runtime_records(result)
        from .compatibility import legacy_case_runtime_conventions

        return with_core_runtime_records(legacy_case_runtime_conventions())


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
        """Source the environment, then configure it. Both halves, always.

        ``get_loaded_environment`` is classified ``single`` in
        `provider_stack.py` -- most-specific provider wins, no combining --
        so sourcing alone cannot reach every provider's runtime contract.
        Configuration (backend/library selection, build-manifest validation)
        is a separate, ``chain``-shape member, ``get_configured_environment``,
        reachable only through :meth:`configure`. Before composition existed,
        a single active plugin's sourcing step ended by reaching
        ``driver_context.plugin``'s configure hook directly (a back-channel
        `openfoam_environment.py`'s ``_configure_plugin_environment`` no
        longer has, by design -- see that function's docstring), so "load"
        always meant "source AND configure" as one step. Restoring that
        combined contract here, via this adapter's own composed
        :meth:`configure`, is what lets every future caller of ``.load()``
        get the correct combined behaviour without every provider's
        ``get_loaded_environment`` needing to remember to configure too.

        Every current call site either calls ``.load()`` alone (`cli.py`'s
        two run/step sites) or ``.configure()`` alone (`sweep_runner.py`'s
        `sweep_run`, on an already-externally-sourced ``os.environ``) --
        never both in sequence -- so this does not double-apply
        configuration anywhere in this repository today.
        """
        hook = getattr(self.plugin, "get_loaded_environment", None)
        if callable(hook):
            sourced = dict(hook(explicit_bashrc=explicit_bashrc, driver_context=driver_context))
        else:
            from .compatibility import legacy_load_environment

            sourced = dict(legacy_load_environment(
                explicit_bashrc=explicit_bashrc, driver_context=driver_context,
            ))
        return self.configure(sourced, driver_context)


@dataclass(frozen=True)
class _OverrideSchemaAdapter:
    plugin: "SolverPlugin"

    def config_schema(
        self, tutorial_name: str, make_spec_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the plugin's config documentation, or the validated schema.

        Two capabilities used to independently author an answer to "what may
        config contain": this one (agent-facing documentation, keyed by
        tutorial) and :class:`RunDocumentConfigurationCapability` (the schema
        core actually validates against). A plugin with real per-tutorial
        vocabulary to document (e.g. cardiacFoam's worked examples) still
        supplies it here and that answer wins unchanged. But when a plugin
        has nothing tutorial-specific to say -- an unrecognized tutorial
        name, or no ``get_override_schema`` hook at all -- the old behaviour
        was a second, independently-authored EMPTY answer (``{}``), which
        documents nothing. That can no longer diverge from the validated
        schema: an empty answer here now derives from
        ``RunDocumentConfigurationCapability.schema()`` instead. (Task 10,
        2026-09-22.)
        """
        hook = getattr(self.plugin, "get_override_schema", None)
        if callable(hook):
            answer = dict(hook(tutorial_name, make_spec_info))
        else:
            from .compatibility import legacy_override_schema

            answer = legacy_override_schema(self.plugin, tutorial_name, make_spec_info)
        if answer:
            return answer
        return _RunDocumentConfigurationAdapter(self.plugin).schema()

    def dict_entry_catalog(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_dict_entry_catalog", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import legacy_dict_entry_catalog

        return legacy_dict_entry_catalog(self.plugin)


@dataclass(frozen=True)
class _RuntimeEvidenceAdapter:
    plugin: "SolverPlugin"

    def solve_step_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_solve_step_commands", None)
        return frozenset(hook()) if callable(hook) else frozenset()

    def telemetry_source_globs(self, command: str) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_telemetry_source_globs", None)
        return tuple(hook(command)) if callable(hook) else ()

    def extra_provenance_paths(self, case_root: Path) -> tuple[RuntimeDependency, ...]:
        hook = getattr(self.plugin, "get_extra_provenance_paths", None)
        return tuple(hook(case_root)) if callable(hook) else ()

    def artifact_value_reader(self, artifact_format: str):
        hook = getattr(self.plugin, "get_artifact_value_reader", None)
        return hook(artifact_format) if callable(hook) else None

    def log_redaction_patterns(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_log_redaction_patterns", None)
        return frozenset(hook()) if callable(hook) else frozenset()


@dataclass(frozen=True)
class _RecordSurfaceAdapter:
    plugin: "SolverPlugin"

    def key_catalog(self, case_root: Path) -> tuple[Mapping[str, Any], ...]:
        hook = getattr(self.plugin, "get_record_key_catalog", None)
        return tuple(hook(case_root)) if callable(hook) else ()

    def guidance(self) -> tuple[Mapping[str, str], ...]:
        hook = getattr(self.plugin, "get_agent_guidance", None)
        return tuple(hook()) if callable(hook) else ()


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

        The context and the execution environment are both passed through to
        the hook -- not just held here -- so an adapter can resolve its own
        transaction and provenance requirements under the caller's context, and
        read each written value back under the caller's runtime, rather than
        substituting either from itself. Core does not delegate to a
        solver-specific mutator when the hook is absent.

        Corrected 2026-09-22 (audit finding F1): ``execution_env`` was accepted
        and forwarded only to ``legacy_apply_overrides``. Every real adapter
        implements the hook, so on the path that runs it was silently dropped,
        and the OpenFOAM implementation answers an absent environment with an
        empty evidence tuple. A required readback was satisfied by evidence
        that was never gathered.
        """
        hook = getattr(self.plugin, "apply_overrides", None)
        if callable(hook):
            records = tuple(
                hook(
                    overrides,
                    case_root=case_root,
                    driver_context=driver_context,
                    execution_env=execution_env,
                )
            )
        else:
            from .compatibility import legacy_apply_overrides

            records = legacy_apply_overrides(
                overrides, case_root=case_root, driver_context=driver_context,
                execution_env=execution_env,
            )
        if execution_env is not None and overrides and not records:
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} applied "
                f"{len(tuple(overrides))} override(s) under an explicit "
                f"execution environment but returned no effective-value "
                f"evidence; an empty record set must not satisfy a required "
                f"readback"
            )
        return records

    def target_paths(
        self, overrides: Any, *, case_root: Any, driver_context: Any,
    ) -> tuple[Path, ...]:
        hook = getattr(self.plugin, "get_override_target_paths", None)
        if callable(hook):
            return tuple(
                Path(path)
                for path in hook(
                    overrides, case_root=case_root, driver_context=driver_context,
                )
            )
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
class _ConfigValueAdapter:
    plugin: "SolverPlugin"

    def reader(self):
        hook = getattr(self.plugin, "get_config_value_reader", None)
        return hook() if callable(hook) else None


@dataclass(frozen=True)
class _DictKeyScannerAdapter:
    plugin: "SolverPlugin"

    def scan(self, source_root: Any, *, allowlist_path: Any, entries: Any) -> Any:
        hook = getattr(self.plugin, "get_dict_key_scanner", None)
        scanner = hook() if callable(hook) else None
        if scanner is None:
            from .compatibility import legacy_dict_key_scanner

            scanner = legacy_dict_key_scanner()
        return scanner(source_root, allowlist_path=allowlist_path, entries=entries)


@dataclass(frozen=True)
class _TutorialRecordAdapter:
    plugin: "SolverPlugin"

    def catalog(self) -> dict[str, Any] | None:
        """``None`` when the plugin declares no hook (review finding M1) --
        not ``{}``, which would be indistinguishable from a plugin that
        implements the hook and simply registers nothing."""
        hook = getattr(self.plugin, "get_tutorial_records", None)
        return dict(hook()) if callable(hook) else None


@dataclass(frozen=True)
class _AxisAdapter:
    plugin: "SolverPlugin"

    def catalog(self) -> dict[str, Any] | None:
        """``None`` when the plugin declares no hook (review finding M1)."""
        hook = getattr(self.plugin, "get_axis_catalog", None)
        return dict(hook()) if callable(hook) else None


@dataclass(frozen=True)
class _RecordKeyValidationAdapter:
    plugin: "SolverPlugin"

    def validator(self) -> Any | None:
        """The plugin's own validator callable, or ``None`` (review finding
        M1) -- no compatibility fallback stands in for a missing one; the
        caller (``record_execution._resolve_and_split``) refuses by name."""
        hook = getattr(self.plugin, "get_record_key_validator", None)
        return hook() if callable(hook) else None


@dataclass(frozen=True)
class _CaseValueComparisonAdapter:
    plugin: "SolverPlugin"

    def comparator(self) -> Any:
        hook = getattr(self.plugin, "get_case_value_comparator", None)
        return hook() if callable(hook) else None


def _resolved_purely(hook, request, *, driver_context):
    """Run a resolution hook and refuse one that touched the case.

    Resolution is declared pure, and a dry run's promise rests on that.

    **What this catches, precisely (R2 finding 12, narrowed 2026-09-23 to
    match what is actually caught rather than what purity would ideally
    mean):** a path added or removed under ``request.case_root`` BETWEEN the
    before- and after-snapshot, taken by name only, via two full ``rglob``
    walks of the case per resolve (including the mesh -- this is not cheap,
    and a mode with a large tree pays it on every resolve, dry run or not).

    **What this does NOT catch:**

    - in-place content modification of a file whose path does not change
      (only names are compared, not digests or mtimes);
    - a permission/mode change (``chmod``) on an existing path;
    - a write outside ``request.case_root`` entirely;
    - a create-then-delete of the same path within one call (the name-set
      comparison sees only the two endpoints, never an intermediate state);
    - any read at all -- reading is not detected, and a resolver that reads
      makes the dry run's result depend on case state at read time, which is
      the entire point of the purity rule this hook exists to enforce. A
      resolver that reads is not "less pure" in some acceptable, partial
      sense; it has silently broken the guarantee a dry run promises, and
      nothing here would tell you.

    A renderer is where filesystem reads belong; it is declared to read.
    """
    root = Path(request.case_root)
    before = set(root.rglob("*")) if root.is_dir() else set()
    resolved = hook(request, driver_context=driver_context)
    after = set(root.rglob("*")) if root.is_dir() else set()
    if before != after:
        changed = sorted(str(p) for p in before ^ after)
        raise ValueError(
            f"resolve_case_mutation() must be pure; "
            f"{request.adapter_id!r} changed {changed}"
        )
    return resolved


@dataclass(frozen=True)
class _CaseWriterAdapter:
    plugin: "SolverPlugin"

    def supported_modes(self) -> "frozenset[str]":
        """Which creation modes this provider supports.

        Three states (R2 finding 0 -- corrected 2026-09-23; the plain
        ``frozenset()`` fix considered and rejected below):

        - the modes hook is present -> its declared set.
        - the modes hook is absent but a resolver is present -> raise, naming
          the provider: an absent-but-resolving provider has NOT declared
          which modes it supports, and defaulting to "every mode" is exactly
          how three installed providers, implementing no resolver hooks
          either, ended up silently claiming to support all of them.
        - both are absent -> ``frozenset()``. Nothing here resolves, so an
          empty set changes nothing: ``resolve()`` below already refuses this
          provider by name before it would ever consult ``supported_modes()``.

        A bare ``frozenset()`` for the middle case would have been the wrong
        fix on its own: ``resolve()`` checks for the ``resolve_case_mutation``
        hook FIRST and refuses by name when it is absent, so a hook-less
        provider never reaches the mode check at all -- and a resolving
        provider that silently supported zero modes would have its every
        request refused with no indication that the omission, not a genuine
        unsupported mode, was the cause.
        """
        modes_hook = getattr(self.plugin, "get_supported_mutation_modes", None)
        if callable(modes_hook):
            return frozenset(modes_hook())
        if callable(getattr(self.plugin, "resolve_case_mutation", None)):
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} implements "
                f"resolve_case_mutation() but declares no "
                f"get_supported_mutation_modes(); which modes it supports is "
                f"undeclared, and defaulting to every mode is how a "
                f"provider implementing no resolver hooks at all came to "
                f"claim it supported all of them"
            )
        return frozenset()

    def resolve(self, request: Any, *, driver_context: Any) -> Any:
        hook = getattr(self.plugin, "resolve_case_mutation", None)
        if not callable(hook):
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} declares no "
                f"resolve_case_mutation(); it authors no case inputs, and an "
                f"empty resolution would silently produce a case that is not "
                f"the one requested"
            )
        supported = self.supported_modes()
        if request.mode not in supported:
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} does not support creation "
                f"mode {request.mode!r}; it supports {sorted(supported)}"
            )
        return _resolved_purely(hook, request, driver_context=driver_context)

    def renderer_for(self, file_format: str) -> str:
        hook = getattr(self.plugin, "get_rendered_formats", None)
        declared = frozenset(hook()) if callable(hook) else frozenset()
        if file_format not in declared:
            raise ValueError(
                f"no provider in this stack renders {file_format!r}; declared "
                f"formats are {sorted(declared)}. A file whose format nobody "
                f"renders stops the plan rather than being dropped from it"
            )
        # `self.plugin` is a `_ComposedProvider` for a composed stack, whose
        # own `.plugin_id` is the most-specific provider -- not necessarily
        # the one that declared `file_format`. `provider_stack.compose`
        # attaches the real per-format map as instance state (not a plugin
        # hook, so read via `vars()` rather than `getattr(self.plugin, ...)`
        # -- the latter pattern is reserved for probing the plugin protocol,
        # see test_every_probed_hook_is_declared_somewhere). A single,
        # uncomposed plugin (as `adapt_plugin_capabilities` is also called
        # directly in tests) carries no such map and is trivially its own
        # declarer.
        declared_by = vars(self.plugin).get("_format_declared_by")
        if declared_by is not None:
            return declared_by[file_format]
        return self.plugin.plugin_id

    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        # Iterated per-provider, not through the pre-composed
        # `render_case_files` sequence callable, so each provider's returned
        # files can be checked against THAT provider's own declared formats
        # before being concatenated (R2 finding 5). Nothing previously
        # checked that a returned `RenderedFile.format` was one the
        # returning provider actually declared via `get_rendered_formats()`,
        # nor that `renderer_id` matched it -- a provider declaring only
        # `other_format` could return a file claiming `openfoam_dictionary`
        # and it would be concatenated alongside the real declarer's,
        # unnoticed. `_check_format_declarers` guards the DECLARATION; this
        # guards the bytes the declaration is supposed to describe.
        try:
            providers = self.plugin.providers
        except AttributeError:
            providers = (self.plugin,)
        rendered: list = []
        saw_renderer = False
        for provider in providers:
            hook = getattr(provider, "render_case_files", None)
            if not callable(hook):
                continue
            saw_renderer = True
            formats_hook = getattr(provider, "get_rendered_formats", None)
            declared = frozenset(formats_hook()) if callable(formats_hook) else frozenset()
            for rendered_file in hook(
                resolved, snapshot_root=snapshot_root,
                driver_context=driver_context, execution_env=execution_env,
            ):
                if rendered_file.format not in declared:
                    raise ValueError(
                        f"provider {provider.plugin_id!r} rendered "
                        f"{rendered_file.path!r} claiming format "
                        f"{rendered_file.format!r}, which it does not declare "
                        f"via get_rendered_formats() (declared: "
                        f"{sorted(declared)}); a provider may only render the "
                        f"formats it declares"
                    )
                if rendered_file.renderer_id != provider.plugin_id:
                    raise ValueError(
                        f"provider {provider.plugin_id!r} rendered "
                        f"{rendered_file.path!r} with renderer_id "
                        f"{rendered_file.renderer_id!r}; a rendered file's "
                        f"renderer_id must name the provider that actually "
                        f"produced it"
                    )
                rendered.append(rendered_file)
        if not saw_renderer:
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} declares no render_case_files()"
            )
        return tuple(rendered)


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
        one of :data:`capability_seams.TIERS` -- ``required`` (called
        unconditionally, no fallback may exist), ``optional-neutral``
        (probed via ``getattr``; the fallback returns a neutral value), or
        ``optional-refusing`` (probed; the fallback raises, naming the
        hook). A capability whose members genuinely differ (``case_files``,
        ``override_scopes``) declares one ``member=tier`` entry per member
        on the same line instead of one tier for the whole seam --
        :func:`capability_seams.status_tiers` reads either shape.
        **Corrected 2026-09-20:** this used to say ``mandatory``/
        ``optional``/``mixed``, free text that let ``_REQUIRED_PLUGIN_MEMBERS``
        disagree with what a Protocol's own docstring claimed. ``:status:``
        is now the single declaration of a member's enforcement tier.

    Those fields are the single source of the "Plugin capability seams" table
    in ``ARCHITECTURE.md``, rendered by
    ``scripts/export-capability-seams.py`` and kept honest by
    ``test_capability_seam_documentation.py`` -- which checks that every
    ``:adapts:`` names a real plugin member and every ``:fallback:`` a real
    compatibility function, so a stale reference fails rather than rots.

    **What a missing optional hook means.** The named fallback runs. No
    fallback branches on plugin identity any more -- Phase 2 Task 7 deleted the
    twenty ``plugin_id == "org.cardiacfoam"`` branches -- so a given fallback
    returns the same answer for every plugin. Two fallbacks cannot be neutral:
    a plugin
    without the sweep hooks is refused by name rather than swept by another
    plugin's writer.
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
    record_surface: RecordSurfaceCapability
    case_provenance: CaseProvenanceCapability
    report_catalog: ReportCatalogCapability
    named_catalogs: NamedCatalogsCapability
    override_scopes: OverrideScopeCapability
    dict_regeneration: DictRegenerationCapability
    config_value: ConfigValueCapability
    dict_key_scanner: DictKeyScannerCapability
    case_writer: CaseWriterCapability
    tutorial_records: TutorialRecordCapability
    axes: AxisCapability
    record_key_validation: RecordKeyValidationCapability
    case_value_comparison: CaseValueComparisonCapability


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
        record_surface=_RecordSurfaceAdapter(plugin),
        case_provenance=_CaseProvenanceAdapter(plugin),
        report_catalog=_ReportCatalogAdapter(plugin),
        named_catalogs=_NamedCatalogsAdapter(plugin),
        override_scopes=_OverrideScopeAdapter(plugin),
        dict_regeneration=_DictRegenerationAdapter(plugin),
        config_value=_ConfigValueAdapter(plugin),
        dict_key_scanner=_DictKeyScannerAdapter(plugin),
        case_writer=_CaseWriterAdapter(plugin),
        tutorial_records=_TutorialRecordAdapter(plugin),
        axes=_AxisAdapter(plugin),
        record_key_validation=_RecordKeyValidationAdapter(plugin),
        case_value_comparison=_CaseValueComparisonAdapter(plugin),
    )
