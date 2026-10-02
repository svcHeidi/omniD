"""Internal, focused capability seams for solver plugins.

Core consumes this bundle instead of reaching through ``DriverContext.plugin``
directly; each capability adapts one plugin concern and degrades through
``compatibility.py`` when the plugin declares no hook for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
    """Input to :class:`RunSemanticValidatorCapability`: a case whose files
    already hold every study value."""

    case_root: Path


@dataclass(frozen=True)
class ArtifactPredictionRequest:
    """Input to :class:`ArtifactPredictorCapability`: the case to inspect and
    the spec it was built from. May name a case that does not exist yet."""

    case_root: Path
    spec: "TutorialSpec"


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
    It does not supply names such as ``postProcessing`` or rules for which
    directories are output instances. A missing declaration is deliberately
    neutral: no authored path is silently removed from a staged case.
    """

    generated_directory_names: tuple[str, ...] = ()
    generated_file_names: tuple[str, ...] = ()
    generated_file_prefixes: tuple[str, ...] = ()
    generated_file_suffixes: tuple[str, ...] = ()
    preserved_file_suffixes: tuple[str, ...] = ()
    generated_case_markers: tuple[str, ...] = ()
    case_entrypoints: tuple[str, ...] = ()
    case_script_commands: tuple[str, ...] = ()
    #: fnmatch globs naming a directory, at any depth in the case tree, that
    #: holds one replica of the case per parallel rank (OpenFOAM:
    #: ``processor*``). Core skips them when staging and discovering cases
    #: at every depth, not only at the case root. Empty: the environment
    #: declares no replicas.
    replica_directory_globs: tuple[str, ...] = ()
    #: Regex a directory name, at any depth in the case tree, matches when
    #: it is one of the solver's output instances (OpenFOAM: a time
    #: directory). ``None``: the environment declares no instances, and core
    #: treats no directory as one. The instance rule also applies to files,
    #: not only directories.
    instance_directory_pattern: str | None = None
    #: Instance names that are authored input and never cleaned (OpenFOAM:
    #: ``"0"``).
    preserved_instance_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a malformed field by name at construction rather than
        corrupting every staged case silently.

        A bare ``str`` for ``replica_directory_globs`` or
        ``preserved_instance_names`` (e.g. ``"processor*"`` instead of
        ``("processor*",)``) explodes into one-character strings under
        ``tuple(...)``, so a naive construction would match or exclude every
        name silently.
        """
        _require_tuple_of_names(self, "replica_directory_globs", noun="glob strings")
        _require_tuple_of_names(self, "preserved_instance_names", noun="name strings")
        if self.instance_directory_pattern is not None:
            if not isinstance(self.instance_directory_pattern, str):
                raise TypeError(
                    f"instance_directory_pattern must be a str or None, got "
                    f"{type(self.instance_directory_pattern).__name__} "
                    f"{self.instance_directory_pattern!r}"
                )
            try:
                re.compile(self.instance_directory_pattern)
            except re.error as exc:
                raise ValueError(
                    f"instance_directory_pattern {self.instance_directory_pattern!r} "
                    f"is not a valid regular expression: {exc}"
                ) from exc


def _require_tuple_of_names(conventions: "CaseRuntimeConventions", field_name: str, *, noun: str) -> None:
    value = getattr(conventions, field_name)
    if not isinstance(value, tuple):
        raise TypeError(
            f"{field_name} must be a tuple of {noun}, got {type(value).__name__} {value!r}"
        )
    for item in value:
        if not isinstance(item, str) or not item:
            raise TypeError(
                f"{field_name} must be a tuple of {noun}, got "
                f"{type(item).__name__} {item!r} among its items"
            )


@dataclass(frozen=True)
class RuntimeDependency:
    """One thing the workflow's *executable* consumes at run time, outside
    the case tree: the solver binary itself, a library it links or loads,
    or a case-local shared object built from sources inside the case.

    ``path is None`` on a ``required=True`` dependency must surface as
    ``unavailable`` rather than silently vanishing from the list -- a plain
    tuple of paths cannot express "required and missing", only omission.
    """

    name: str
    path: Path | None
    required: bool


class DictionaryCatalogCapability(Protocol):
    """The plugin's dictionary vocabulary, in three shapes for three callers.

    ``entries`` is the flat tuple of ``DictEntry`` values; ``catalog`` is the
    same data as a queryable ``DictionaryCatalog`` (``entries_for(document)``);
    ``groups`` buckets entries by the plugin's own group names; ``documents``
    arranges them by the plugin's own document names, unserialized. Core does
    not know those names -- ``electroProperties`` is cardiac vocabulary, and a
    solids4foam plugin would say ``solidProperties`` instead.

    All are optional-neutral. A plugin without dictionaries (openCARP, the
    toy) omits them, and each answers empty: ``()``, ``DictionaryCatalog({})``,
    ``{}``. This is the seam that keeps dictionary *syntax* knowledge (core's)
    apart from dictionary *meaning* (the plugin's).

    :adapts: get_dict_entries, get_dict_groups, get_dict_entry_catalog, get_dictionary_catalog
    :consumed-by: omnidriver/dict_entries.py, omnidriver/cardiacfoam/dict_entries.py, omnidriver/openfoam/plan_diagnostics.py, omnidriver/core/catalog_query.py
    :fallback: absent_dict_entry_catalog
    :status: optional-neutral
    """

    def entries(self) -> tuple[Any, ...]: ...
    def catalog(self) -> Any: ...
    def groups(self) -> dict[str, tuple[Any, ...]]: ...
    def documents(self) -> dict[str, Any]: ...


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
    """The catalogue's relations and the solver's cross-field rules, judged
    over a resolved case before anything runs: every error refuses the record
    case by name. Distinct from :class:`ConfigurationValidatorCapability`,
    which judges a ``TutorialSpec``. Required v1 member, no fallback.

    :adapts: validate_run_semantics
    :consumed-by: omnidriver/core/runtime/record_execution.py
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


class CxxMappingCapability(Protocol):
    """The plugin's declarative profile: case-file rules and C++ provenance.

    Sourced from the plugin's ``plugin.yaml`` via ``get_profile()``. Named for
    the C++ source mapping it carries (which solver sources back which
    dictionary keys, used for provenance fingerprinting), but the same profile
    also backs :class:`CaseFileContractCapability`.

    :adapts: get_profile
    :consumed-by: omnidriver/core/catalog_query.py, omnidriver/openfoam/plan_diagnostics.py
    :fallback: none
    :status: required
    """

    def profile(self) -> Any: ...


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
    :fallback: absent_auxiliary_commands, absent_environment_commands, absent_is_installed_environment_command, absent_solver_commands, absent_utility_manifests, absent_utility_roots
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

    The resumed-from start-time directory is a separate concern, declared
    through ``CaseProvenanceCapability.input_roots``.

    :adapts: get_samplable_fields, resolve_case_models
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: absent_resolve_case_models, absent_samplable_fields
    :status: optional-neutral
    """

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]: ...
    def samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]: ...


class CaseFileContractCapability(Protocol):
    """Which case files the active plugin's profile declares.

    Sourced directly from ``PluginProfile.case_files``: ``all_rules`` returns
    every declared rule with its ``role`` intact, whether the file is
    ``required`` always or only conditionally.

    **Roles are namespaced and the prefix is load-bearing.** Core owns only
    its documented namespaces; every other namespace belongs to the adapter.
    For example, the OpenFOAM adapter uses ``openfoam.*`` and the solver may
    use ``plugin.*``. Consumers classify ownership from the namespace, not
    from a hard-coded file path. ``get_profile()`` is a required v1 member, so
    every adapter carries this data and no compatibility fallback is needed.

    ``get_profile`` deliberately backs this capability AND
    ``CxxMappingCapability``: one declaration, two consumers with different
    concerns, not a duplicate intake.

    :adapts: get_profile
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py, omnidriver/core/runtime/record_surface.py
    :fallback: none
    :status: required
    """

    def all_rules(self) -> tuple["CaseFileRule", ...]: ...


class CaseRuntimeConventionsCapability(Protocol):
    """Generated-path and output-root declarations for one environment.

    A staging transaction needs to distinguish reusable authored inputs from
    derived output. That is a Core mechanism. The path names are
    environment conventions, so this capability supplies them as data. A
    plugin without the optional hook receives only core's own run records
    (``runtime_records.CORE_RUNTIME_RECORDS``, merged into every answer):
    core preserves every authored path and does not collect a
    convention-specific tree.

    :adapts: get_case_runtime_conventions
    :consumed-by: omnidriver/core/runtime/sweep_runner.py
    :fallback: absent_case_runtime_conventions
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

    ``diagnostics`` and ``load`` both take ``environment_source``: one opaque
    string, or ``None``, the operator supplies with ``--environment-source``.
    Core passes it through and never reads it; what it names is the plugin's
    business. The OpenFOAM layer sources it as a shell script; openCARP
    ignores it.

    :adapts: get_environment_diagnostics, get_configured_environment, get_loaded_environment
    :consumed-by: omnidriver/core/strict_planning.py, omnidriver/core/runtime/sweep_runner.py, omnidriver/cli.py, omnidriver/conformance/checks.py
    :fallback: absent_environment_diagnostics, absent_configured_environment, absent_load_environment
    :status: optional-neutral
    """

    def diagnostics(
        self,
        workflow_dag: dict[str, Any] | None,
        *,
        env: dict[str, str] | None = None,
        environment_source: str | None = None,
        driver_context: Any | None = None,
    ) -> tuple[Any, ...]: ...

    def configure(
        self, env: dict[str, str], driver_context: Any | None,
    ) -> dict[str, str]: ...


class PlanDiagnosticsCapability(Protocol):
    """What a solver stack adds to a strict plan's diagnostics.

    Every stack has the stages core reports on its own (workflow, artifacts,
    environment). What else a plan can say about a case -- a catalogue the
    solver's source contradicts, a sampled field the model does not expose, a
    case key nothing reads -- depends on the solver's file formats, which core
    does not know. The hook returns ``StrictDiagnostic`` values; an error
    fails the plan, a warning or note never does. Composed by concatenation in
    stack order.

    ``scratch_root`` is where the supplied scratch root lets a stack cache work
    derived from its own inputs (``None`` when none was supplied).

    :adapts: get_plan_diagnostics
    :consumed-by: omnidriver/core/strict_planning.py
    :fallback: none
    :status: optional-neutral
    """

    def diagnostics(
        self,
        case_root: Path,
        *,
        workflow_dag: dict[str, Any] | None,
        env: Mapping[str, str],
        scratch_root: Path | None,
        driver_context: Any,
    ) -> tuple[Any, ...]: ...


class StepFailureCapability(Protocol):
    """What a solver's own words in a failed step's log mean for the case.

    A solver stops with a message naming what it could not find; the exit code
    says only that it stopped. The hook reads the log tail and returns
    ``StrictDiagnostic`` values the step's failure carries, so an agent reads
    the key and the dictionary rather than a log. Composed by concatenation in
    stack order.

    :adapts: explain_step_failure
    :consumed-by: omnidriver/core/runtime/workflow_runner.py
    :fallback: none
    :status: optional-neutral
    """

    def diagnostics(self, log_text: str, case_root: Path, *, driver_context: Any) -> tuple[Any, ...]: ...


class RuntimeEvidenceCapability(Protocol):
    """Where the plugin's runtime evidence lives.

    ``artifact_value_reader(format)`` returns the reader for one artifact
    format (``core.quantities.ArtifactValueReader``) or ``None``. A ``None``
    makes that artifact's quantities ``not_evaluated`` with the format
    named, never an implicit pass.

    Telemetry collection consumes ``solve_step_commands`` and
    ``telemetry_source_globs``; provenance consumes
    ``extra_provenance_paths``. ``solve_step_commands`` is also how
    ``record_execution`` finds a record's solve step, the one a parallel
    request rewrites.

    Every member degrades to empty for a plugin that declares nothing, which
    is the honest answer rather than a solver-shaped guess -- so this
    capability needs no compatibility fallback.

    :adapts: get_artifact_value_reader, get_extra_provenance_paths, get_log_redaction_patterns, get_solve_step_commands, get_telemetry_source_globs
    :consumed-by: omnidriver/conformance/checks.py, omnidriver/core/quantities/comparison.py, omnidriver/core/runtime/provenance_inputs.py, omnidriver/core/runtime/record_execution.py, omnidriver/core/runtime/workflow_runner.py
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
        are not kept."""
        ...


class RecordSurfaceCapability(Protocol):
    """What an agent may address in a record, and what it should read first.

    Discovering a record's keys and guidance must not depend on knowing
    which solver is underneath. ``key_catalog`` lists the keys a study may
    name for a case; ``guidance`` is solver-level advice for agents. Both
    degrade to empty, which the conformance suite reports as a failure for a
    real target.

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

    Each takes the resolved case dictionaries (not just the model name),
    because gating is by dictionary *value*: e.g. ``conductivitySource field``
    vs ``uniform`` flips a mandatory read on and off, and an absent key
    silently defaults to ``uniform``.

    ``input_roots`` names the case-relative directories, beyond the case-file
    roots, whose files a run reads as state. For OpenFOAM, that is the
    selected start-time directory and the same directory in every parallel
    replica. Core walks each and classifies its files by the same precedence.
    Absent: ``()``, and core walks no state directory.

    Composes as ``sequence`` (``provider_stack._SHAPE``), not ``single``: every
    provider in the stack that implements the hook contributes its own roots,
    concatenated, rather than the most specific provider's answer replacing
    the rest. A more specific provider can only add required inputs, never
    remove one a less specific provider declared, since the superset can only
    make a case's provenance MORE complete.

    ``conventions`` is the stack's merged ``CaseRuntimeConventions`` -- the
    same value ``case_runtime_conventions.conventions()`` returns, and the
    same source staging/discovery/snapshotting read, so a plugin stacked on
    top of OpenFOAM that declares a *different* ``replica_directory_globs``
    has its replicas honoured consistently by staging, discovery and
    provenance rather than walked past unfingerprinted by one of the three.

    Routed through the capability adapter exactly like every other plugin
    capability -- deliberately **not** a mandatory ``SolverPlugin``
    member, so existing v2 third-party plugins keep loading. The adapter's
    fallback returns empty for both, which under the resolution precedence
    (a DAG step's ``consumes``, then a plugin's ``required_inputs``, then
    ``generated_output_globs``, then: unknown files are ``required_input``)
    means "everything unknown is a required input" -- the safe default for
    a plugin that declares nothing.

    :adapts: get_generated_output_globs, get_input_roots, get_required_inputs
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: none
    :status: optional-neutral
    """

    def input_roots(
        self, case_root: Path, resolved_case: dict[str, Any],
        *, conventions: CaseRuntimeConventions,
    ) -> tuple[str, ...]: ...

    def required_inputs(
        self, case_root: Path, resolved_case: dict[str, Any],
    ) -> tuple[ResolvedInput, ...]: ...

    def generated_output_globs(
        self, case_root: Path, resolved_case: dict[str, Any],
    ) -> tuple[str, ...]: ...


class ReportCatalogCapability(Protocol):
    """Post-run report definitions the active plugin wants offered.

    ``report_catalog`` (:mod:`omnidriver.core.report_catalog`) owns the
    solver-neutral machinery -- ``ReportDefinition``, the ``applicable_when``
    predicate evaluator, the JSON record shape -- but the *catalog itself*
    (which reports exist, e.g. "Vm field" or "activation map") is
    adapter-specific data. Not a mandatory ``SolverPlugin`` member, so
    existing v2 third-party plugins keep loading; the fallback
    (``absent_report_catalog``) is empty until an adapter declares reports.

    :adapts: get_report_catalog
    :consumed-by: scripts/export-report-catalog.py
    :fallback: absent_report_catalog
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
    keep loading; the fallback (``absent_named_catalogs``) is empty until an
    adapter declares its own catalogs.

    :adapts: get_named_catalogs
    :consumed-by: omnidriver/core/introspection.py
    :fallback: absent_named_catalogs
    :status: optional-neutral
    """

    def catalogs(self) -> dict[str, Any]: ...


class ConfigValueCapability(Protocol):
    """Read one configuration value from an adapter's own file format.

    Not a mandatory ``SolverPlugin`` member, so existing v2 third-party
    plugins keep loading; a plugin that declares nothing has no
    adapter-specific format to read, which is the honest answer rather than
    a solver-shaped guess -- so this capability needs no compatibility
    fallback.

    :adapts: get_config_value_reader
    :consumed-by: omnidriver/core/runtime/record_execution.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def reader(self): ...


class EffectiveConfigurationCapability(Protocol):
    """The files a case's configuration depends on, read without running
    anything: what the adapter's own format resolves, files outside the
    case included.

    Strict planning reports what it finds, and provenance fingerprints it,
    so a later edit to an included file invalidates a reused run. A plugin
    that declares nothing contributes no evidence.

    :adapts: inspect_effective_configuration
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py, omnidriver/core/strict_planning.py
    :fallback: absent_inspect_effective_configuration
    :status: optional-neutral
    """

    def inspect(
        self, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]: ...


class DictKeyScannerCapability(Protocol):
    """Compare an adapter's dictionary catalogue with what its C++ reads.

    The scan is C++/dictionary-format knowledge, so it belongs to the
    environment adapter (``omnidriver-openfoam``), not to a solver plugin.
    The report's JSON carries ``disagreements`` (catalogue claims the C++
    refutes, each stating both sides), ``unread`` (catalogued keys the C++ no
    longer reads), ``uncatalogued`` (what the C++ reads and the catalogue
    lacks, with the entry arguments the scan can fill), ``unresolved`` (reads
    the scan could not place) and ``selector_values``. None of them fails a
    plan.
    ``cache_root`` keeps the scan between processes; ``force`` rescans. The
    fallback (``absent_dict_key_scanner``) reports nothing.

    :adapts: get_dict_key_scanner
    :consumed-by: omnidriver/openfoam/plan_diagnostics.py, omnidriver/core/catalog_query.py
    :fallback: absent_dict_key_scanner
    :status: optional-neutral
    """

    def scan(
        self, source_root: Any, *, allowlist_path: Any, entries: Any,
        cache_root: Any = None, force: bool = False,
    ) -> Any: ...


class TutorialRecordCapability(Protocol):
    """The tutorial records this plugin registers -- data, not factories.

    A record (``core.tutorial_records.TutorialRecord``) names a native case
    path relative to the environment's own cases root, its own axes, and its
    workflow steps. A record names the axes it allows itself, so two records
    cannot give one axis name two meanings. Resolving a record calls no
    plugin code at all, until an axis it names actually runs (see
    ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
    §3). ``tutorial_records.lookup_record`` resolves an entry name in this
    catalog.

    **No fallback.** ``catalog()`` returns ``None``, not ``{}``, when the
    plugin declares no ``get_tutorial_records`` hook at all -- distinct from
    a plugin that implements the hook and simply registers no records yet.
    ``lookup_record`` treats ``None`` as "this stack registers no tutorial
    records" rather than iterating a fabricated empty mapping.

    :adapts: get_tutorial_records
    :consumed-by: omnidriver/core/tutorial_records.py, omnidriver/conformance/checks.py
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

    **No fallback.** A stack with no validator has no catalog to check ANY
    direct key -- or any axis-produced patch -- against.
    ``record_execution._resolve_and_split`` reads ``validator() is None`` and
    REFUSES BY NAME before running a record case at all, rather than letting
    every key silently through unchecked.

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
    ``record_execution._resolve_and_split`` reads ``comparator() is None``
    first and REFUSES BY NAME before running a record case at all: a stack
    that cannot tell "unchanged" from "changed" must not silently report
    every no-op as a change and commit it.

    **No fallback.**

    :adapts: get_case_value_comparator
    :consumed-by: omnidriver/core/runtime/record_execution.py, omnidriver/conformance/checks.py
    :fallback: none
    :status: optional-neutral
    """

    def comparator(self) -> Any: ...


class ParallelExecutionCapability(Protocol):
    """The parallel form of a record's solve step, if the stack has one.

    Serial versus parallel belongs to the solver's own layer, which must
    know how to run it; a record declares its solve step once and carries no
    parallel variant. ``steps_for()`` returns the
    stack's ``get_parallel_steps`` callable (contract on
    ``SolverPluginOptionalHooks``), or ``None``. ``record_execution
    ._parallel_workflow_dag`` calls it for each step whose command the stack
    declares in ``get_solve_step_commands``, rewires the DAG around what it
    returns, and refuses by name when a run asks for parallel and this is
    ``None``. A serial run never consults it, so a stack without it runs
    exactly as before.

    :adapts: get_parallel_steps
    :consumed-by: omnidriver/core/runtime/record_execution.py
    :fallback: none
    :status: optional-neutral
    """

    def steps_for(self) -> Any | None: ...


class CaseWriterCapability(Protocol):
    """How a framework-authored case mutation becomes reviewable bytes.

    Three answers from up to three owners. ``resolve`` is the selected
    adapter's and is pure. ``render`` belongs to whichever provider declares
    the file's format, one declarer per format. Committing is core's and is not
    here at all -- see :mod:`omnidriver.core.case_transaction`.

    The fallback cannot be neutral for any of the four members. An empty
    resolution silently yields a case that is not the one requested, so an
    adapter without these hooks is refused by name; ``get_rendered_formats``'s
    own fallback returns a neutral ``frozenset()``, but ``render`` then refuses
    BY NAME any file whose format that set does not declare. See ``_CaseWriterAdapter.supported_modes`` for the
    three-state resolver/mode logic.

    :adapts: resolve_case_mutation, get_supported_mutation_modes, get_rendered_formats, render_case_files
    :consumed-by: none
    :fallback: none
    :status: resolve_case_mutation=optional-refusing, get_supported_mutation_modes=optional-refusing, get_rendered_formats=optional-refusing, render_case_files=optional-refusing
    """

    def resolve(self, request: Any, *, driver_context: Any) -> Any: ...
    def supported_modes(self) -> "frozenset[str]": ...
    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]: ...


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

    def documents(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_dict_entry_catalog", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import absent_dict_entry_catalog

        return absent_dict_entry_catalog(self.plugin)


@dataclass(frozen=True)
class _CapabilityManifestAdapter:
    """Assembles the accept-surface manifest, merging in only what a plugin
    alone can supply (a domain catalogue such as cardiacFoam's ionic-model
    table); the ``allowed_commands``/``samplable_fields`` sections are built
    from the same composed capability reads every other adapter here uses,
    not handed back whole by the plugin. Not cached: recomputing costs
    nothing, and a cached dict shared across every caller of one
    ``DriverContext`` would narrow the isolation it exists to provide.
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
        return self.plugin.validate_run_semantics(request.case_root)


@dataclass(frozen=True)
class _ArtifactPredictorAdapter:
    plugin: "SolverPlugin"

    def predict(self, request: ArtifactPredictionRequest) -> tuple["DataArtifact", ...]:
        return self.plugin.predict_data_artifacts(request.case_root, request.spec)


@dataclass(frozen=True)
class _CxxMappingAdapter:
    plugin: "SolverPlugin"

    def profile(self) -> Any:
        return self.plugin.get_profile()


@dataclass(frozen=True)
class _CommandAuthorizationAdapter:
    plugin: "SolverPlugin"

    def solver_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_solver_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import absent_solver_commands

        return absent_solver_commands(self.plugin)

    def auxiliary_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_auxiliary_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import absent_auxiliary_commands

        return absent_auxiliary_commands(self.plugin)

    def environment_commands(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_environment_commands", None)
        if callable(hook):
            return frozenset(hook())
        from .compatibility import absent_environment_commands

        return absent_environment_commands(self.plugin)

    def is_installed_environment_command(self, command: str) -> bool:
        hook = getattr(self.plugin, "is_installed_environment_command", None)
        if callable(hook):
            return bool(hook(command))
        from .compatibility import absent_is_installed_environment_command

        return absent_is_installed_environment_command(self.plugin, command)

    def utility_manifests(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_utility_manifests", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import absent_utility_manifests

        return absent_utility_manifests(self.plugin)

    def utility_roots(self) -> tuple[Path, ...]:
        hook = getattr(self.plugin, "get_utility_roots", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import absent_utility_roots

        return absent_utility_roots(self.plugin)


@dataclass(frozen=True)
class _CaseIntrospectionAdapter:
    plugin: "SolverPlugin"

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        hook = getattr(self.plugin, "resolve_case_models", None)
        if callable(hook):
            return dict(hook(case_root))
        from .compatibility import absent_resolve_case_models

        return absent_resolve_case_models(self.plugin, case_root)

    def samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        hook = getattr(self.plugin, "get_samplable_fields", None)
        if callable(hook):
            return {k: tuple(v) for k, v in hook(resolved).items()}
        from .compatibility import absent_samplable_fields

        return absent_samplable_fields(self.plugin, resolved)


@dataclass(frozen=True)
class _CaseFileContractAdapter:
    plugin: "SolverPlugin"

    def all_rules(self) -> tuple["CaseFileRule", ...]:
        return tuple(self.plugin.get_profile().case_files)


@dataclass(frozen=True)
class _CaseRuntimeConventionsAdapter:
    plugin: "SolverPlugin"

    def conventions(self) -> CaseRuntimeConventions:
        """The stack's declared generated paths, plus core's own run records
        (``runtime_records.CORE_RUNTIME_RECORDS``), whatever the plugin
        declares -- a plugin without the hook must still get core's own run
        records, or staging a case a run had written carries core's own
        state into the next stage."""
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
        from .compatibility import absent_case_runtime_conventions

        return with_core_runtime_records(absent_case_runtime_conventions())


@dataclass(frozen=True)
class _EnvironmentPreflightAdapter:
    plugin: "SolverPlugin"

    def diagnostics(
        self,
        workflow_dag: dict[str, Any] | None,
        *,
        env: dict[str, str] | None = None,
        environment_source: str | None = None,
        driver_context: Any | None = None,
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_environment_diagnostics", None)
        if callable(hook):
            return tuple(hook(
                workflow_dag, env=env, environment_source=environment_source,
                driver_context=driver_context,
            ))
        from .compatibility import absent_environment_diagnostics

        return tuple(absent_environment_diagnostics(
            workflow_dag, env=env, environment_source=environment_source,
            driver_context=driver_context,
        ))

    def configure(
        self, env: dict[str, str], driver_context: Any | None,
    ) -> dict[str, str]:
        hook = getattr(self.plugin, "get_configured_environment", None)
        if callable(hook):
            return dict(hook(env, driver_context))
        from .compatibility import absent_configured_environment

        return dict(absent_configured_environment(env, driver_context))

    def load(
        self, *, environment_source: str | None, driver_context: Any | None,
    ) -> dict[str, str]:
        """Source the environment, then configure it. Both halves, always.

        ``get_loaded_environment`` is a ``single``-shape member (most-specific
        provider wins, no combining), so sourcing alone cannot reach every
        provider's runtime contract; configuration is the separate
        ``chain``-shape ``get_configured_environment``, reachable only
        through :meth:`configure`. Composing both here is what lets every
        caller of ``.load()`` get the correct combined behaviour without
        every provider remembering to configure too.
        """
        hook = getattr(self.plugin, "get_loaded_environment", None)
        if callable(hook):
            sourced = dict(hook(environment_source=environment_source, driver_context=driver_context))
        else:
            from .compatibility import absent_load_environment

            sourced = dict(absent_load_environment(
                environment_source=environment_source, driver_context=driver_context,
            ))
        return self.configure(sourced, driver_context)


@dataclass(frozen=True)
class _PlanDiagnosticsAdapter:
    plugin: "SolverPlugin"

    def diagnostics(
        self,
        case_root: Path,
        *,
        workflow_dag: dict[str, Any] | None,
        env: Mapping[str, str],
        scratch_root: Path | None,
        driver_context: Any,
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "get_plan_diagnostics", None)
        if not callable(hook):
            return ()
        return tuple(hook(
            case_root, workflow_dag=workflow_dag, env=env,
            scratch_root=scratch_root, driver_context=driver_context,
        ))


@dataclass(frozen=True)
class _StepFailureAdapter:
    plugin: "SolverPlugin"

    def diagnostics(self, log_text: str, case_root: Path, *, driver_context: Any) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "explain_step_failure", None)
        if not callable(hook):
            return ()
        return tuple(hook(log_text, case_root, driver_context=driver_context))


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

    def input_roots(
        self, case_root: Path, resolved_case: dict[str, Any],
        *, conventions: CaseRuntimeConventions,
    ) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_input_roots", None)
        if not callable(hook):
            return ()
        roots = tuple(hook(case_root, resolved_case, conventions=conventions))
        for root in roots:
            # str only: a pathlib.Path is a natural but wrong type here.
            if not isinstance(root, str):
                raise TypeError(
                    f"{self.plugin.plugin_id}.get_input_roots() must return "
                    f"`str` case-relative paths, got {type(root).__name__}"
                )
            # A blank root is not "no opinion": ``case_root / ""`` is the whole
            # case tree. An absolute or escaping root walks outside the case.
            # Refused by name, never silently misclassified.
            parts = PurePosixPath(root).parts
            if not parts or PurePosixPath(root).is_absolute() or ".." in parts:
                raise TypeError(
                    f"{self.plugin.plugin_id}.get_input_roots() must return non-empty "
                    f"case-relative paths inside the case, got {root!r}"
                )
        return roots

    def required_inputs(
        self, case_root: Path, resolved_case: dict[str, Any],
    ) -> tuple[ResolvedInput, ...]:
        hook = getattr(self.plugin, "get_required_inputs", None)
        if callable(hook):
            return tuple(hook(case_root, resolved_case))
        return ()

    def generated_output_globs(
        self, case_root: Path, resolved_case: dict[str, Any],
    ) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_generated_output_globs", None)
        if callable(hook):
            return tuple(hook(case_root, resolved_case))
        return ()


@dataclass(frozen=True)
class _ReportCatalogAdapter:
    plugin: "SolverPlugin"

    def reports(self) -> tuple["ReportDefinition", ...]:
        hook = getattr(self.plugin, "get_report_catalog", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import absent_report_catalog

        return absent_report_catalog(self.plugin)


@dataclass(frozen=True)
class _NamedCatalogsAdapter:
    plugin: "SolverPlugin"

    def catalogs(self) -> dict[str, Any]:
        hook = getattr(self.plugin, "get_named_catalogs", None)
        if callable(hook):
            return dict(hook())
        from .compatibility import absent_named_catalogs

        return absent_named_catalogs(self.plugin)


@dataclass(frozen=True)
class _ConfigValueAdapter:
    plugin: "SolverPlugin"

    def reader(self):
        hook = getattr(self.plugin, "get_config_value_reader", None)
        return hook() if callable(hook) else None


@dataclass(frozen=True)
class _EffectiveConfigurationAdapter:
    plugin: "SolverPlugin"

    def inspect(
        self, *, case_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        hook = getattr(self.plugin, "inspect_effective_configuration", None)
        if callable(hook):
            return tuple(hook(case_root=case_root, execution_env=execution_env))
        from .compatibility import absent_inspect_effective_configuration

        return absent_inspect_effective_configuration(
            case_root=case_root,
            driver_context=driver_context,
            execution_env=execution_env,
        )


@dataclass(frozen=True)
class _DictKeyScannerAdapter:
    plugin: "SolverPlugin"

    def scan(
        self, source_root: Any, *, allowlist_path: Any, entries: Any,
        cache_root: Any = None, force: bool = False,
    ) -> Any:
        hook = getattr(self.plugin, "get_dict_key_scanner", None)
        scanner = hook() if callable(hook) else None
        if scanner is None:
            from .compatibility import absent_dict_key_scanner

            scanner = absent_dict_key_scanner()
        return scanner(
            source_root, allowlist_path=allowlist_path, entries=entries, cache_root=cache_root, force=force,
        )


@dataclass(frozen=True)
class _TutorialRecordAdapter:
    plugin: "SolverPlugin"

    def catalog(self) -> dict[str, Any] | None:
        """``None`` when the plugin declares no hook -- not ``{}``, which
        would be indistinguishable from a plugin that implements the hook
        and simply registers nothing."""
        hook = getattr(self.plugin, "get_tutorial_records", None)
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


@dataclass(frozen=True)
class _ParallelExecutionAdapter:
    plugin: "SolverPlugin"

    def steps_for(self) -> Any | None:
        """The stack's own ``get_parallel_steps``, or ``None``; no fallback
        stands in for a missing one (the caller refuses by name)."""
        hook = getattr(self.plugin, "get_parallel_steps", None)
        return hook if callable(hook) else None


def _resolved_purely(hook, request, *, driver_context):
    """Run a resolution hook and refuse one that touched the case.

    Resolution is declared pure, and a dry run's promise rests on that. The
    check compares path names under ``request.case_root`` before and after
    (two full ``rglob`` walks, not cheap for a large mesh); it does not catch
    in-place content edits, permission changes, writes outside the case root,
    a create-then-delete within one call, or any read -- a resolver that
    reads makes a dry run's result depend on case state at read time, which
    breaks the purity guarantee silently. A renderer is where filesystem
    reads belong.
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

        Three states: the modes hook present -> its declared set; absent but
        a resolver is present -> raise, naming the provider (which modes it
        supports is undeclared, and defaulting to "every mode" is how a
        provider implementing no resolver hooks either would silently claim
        to support all of them); both absent -> ``frozenset()``, which
        changes nothing since ``resolve()`` already refuses a hook-less
        provider by name before consulting this.
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

    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        # Iterated per-provider, not through the pre-composed
        # `render_case_files` sequence callable, so each provider's returned
        # files can be checked against THAT provider's own declared formats
        # and `renderer_id` before being concatenated -- otherwise a provider
        # declaring only `other_format` could return a file claiming
        # `openfoam_dictionary` unnoticed.
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
        ``case_writer``) declares one ``member=tier`` entry per member
        on the same line instead of one tier for the whole seam --
        :func:`capability_seams.status_tiers` reads either shape.
        ``:status:`` is the single declaration of a member's enforcement
        tier.

    Those fields are the single source of the "Plugin capability seams" table
    in ``ARCHITECTURE.md``, rendered by
    ``scripts/export-capability-seams.py`` and kept honest by
    ``test_capability_seam_documentation.py`` -- which checks that every
    ``:adapts:`` names a real plugin member and every ``:fallback:`` a real
    compatibility function, so a stale reference fails rather than rots.

    **What a missing optional hook means.** The named fallback runs. No
    fallback branches on plugin identity, so a given fallback returns the
    same answer for every plugin.
    """

    dictionaries: DictionaryCatalogCapability
    manifest: CapabilityManifestCapability
    configuration_validator: ConfigurationValidatorCapability
    run_semantic_validator: RunSemanticValidatorCapability
    artifacts: ArtifactPredictorCapability
    cxx_mapping: CxxMappingCapability
    command_authorization: CommandAuthorizationCapability
    case_introspection: CaseIntrospectionCapability
    case_files: CaseFileContractCapability
    case_runtime_conventions: CaseRuntimeConventionsCapability
    environment_preflight: EnvironmentPreflightCapability
    plan_diagnostics: PlanDiagnosticsCapability
    step_failure: StepFailureCapability
    runtime_evidence: RuntimeEvidenceCapability
    record_surface: RecordSurfaceCapability
    case_provenance: CaseProvenanceCapability
    report_catalog: ReportCatalogCapability
    named_catalogs: NamedCatalogsCapability
    config_value: ConfigValueCapability
    effective_configuration: EffectiveConfigurationCapability
    dict_key_scanner: DictKeyScannerCapability
    case_writer: CaseWriterCapability
    tutorial_records: TutorialRecordCapability
    record_key_validation: RecordKeyValidationCapability
    case_value_comparison: CaseValueComparisonCapability
    parallel_execution: ParallelExecutionCapability


def adapt_plugin_capabilities(plugin: "SolverPlugin") -> PluginCapabilities:
    """Wrap one loaded plugin in the capability bundle core consumes.

    Called once per :class:`~omnidriver.core.plugin_interface.DriverContext`
    and cheap: every adapter is a frozen dataclass holding the plugin, and no
    plugin member is called here. Optional hooks are probed lazily at each
    call site, so a plugin missing one is adapted successfully and degrades
    only when that capability is actually used.
    """

    return PluginCapabilities(
        dictionaries=_DictionaryCatalogAdapter(plugin),
        manifest=_CapabilityManifestAdapter(plugin),
        configuration_validator=_ConfigurationValidatorAdapter(plugin),
        run_semantic_validator=_RunSemanticValidatorAdapter(plugin),
        artifacts=_ArtifactPredictorAdapter(plugin),
        cxx_mapping=_CxxMappingAdapter(plugin),
        command_authorization=_CommandAuthorizationAdapter(plugin),
        case_introspection=_CaseIntrospectionAdapter(plugin),
        case_files=_CaseFileContractAdapter(plugin),
        case_runtime_conventions=_CaseRuntimeConventionsAdapter(plugin),
        environment_preflight=_EnvironmentPreflightAdapter(plugin),
        plan_diagnostics=_PlanDiagnosticsAdapter(plugin),
        step_failure=_StepFailureAdapter(plugin),
        runtime_evidence=_RuntimeEvidenceAdapter(plugin),
        record_surface=_RecordSurfaceAdapter(plugin),
        case_provenance=_CaseProvenanceAdapter(plugin),
        report_catalog=_ReportCatalogAdapter(plugin),
        named_catalogs=_NamedCatalogsAdapter(plugin),
        config_value=_ConfigValueAdapter(plugin),
        effective_configuration=_EffectiveConfigurationAdapter(plugin),
        dict_key_scanner=_DictKeyScannerAdapter(plugin),
        case_writer=_CaseWriterAdapter(plugin),
        tutorial_records=_TutorialRecordAdapter(plugin),
        record_key_validation=_RecordKeyValidationAdapter(plugin),
        case_value_comparison=_CaseValueComparisonAdapter(plugin),
        parallel_execution=_ParallelExecutionAdapter(plugin),
    )
