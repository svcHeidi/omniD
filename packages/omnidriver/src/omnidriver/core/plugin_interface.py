"""Solver-agnostic plugin contract for omnidriver.

Two Protocol classes define what a solver plugin must implement:

- :class:`SolverPlugin` — the plugin contract, enforced in full by
  :func:`validate_plugin`.
- :class:`SolverPluginOptionalHooks` — the probe-based optional hooks that
  unlock additional capabilities (sweeps, mesh diagnostics, report catalogs,
  override scopes, …).  **Read this class** to discover all extension points
  before deciding your plugin is complete.

Use :func:`driver_context` or :func:`load_plugin_context` to create a
validated, immutable :class:`DriverContext` for each public operation.
Adapters may provide their own context factories for convenience, and
:func:`default_driver_context` only at compatibility boundaries.

Environment and solver adapters implement this contract directly. See
``AGENT_GUIDE.md``, section "Plugin Guide -- Adding a New Solver".
2026-09-14: this previously pointed at
``.agents/skills/driverfoam-plugin-builder/SKILL.md``, a path that lived
in the pre-migration cardiacFOAM tree and exists in no repository now.
2026-09-20: the ``SolverPlugin`` bullet previously said "27 required
members." That count went stale the moment :func:`_required_plugin_members`
started deriving the required set from the capability seams' ``:status:``
tiers instead of a hand-maintained literal; counting members in prose is
exactly what rotted here, so the number is not restated.
"""

# REQUIRED, not stylistic. Several annotations below name types imported only
# under ``if TYPE_CHECKING`` (DictEntry, TutorialSpec, TutorialDisplay,
# DataArtifact, Path). Without lazy annotations those are evaluated when the
# class body executes, so importing this module raises
# ``NameError: name 'DictEntry' is not defined`` on every Python before 3.14 --
# i.e. on 3.11/3.12, which is exactly this project's CI matrix. Python 3.14's
# PEP 649 defers annotation evaluation and hides the bug, which is why a 3.14
# virtualenv shows a green suite while CI cannot collect a single test.
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from dataclasses import dataclass, field
from functools import cached_property
from importlib import import_module
from typing import Any, Mapping, Protocol, Sequence, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from omnidriver.core.plugin_capabilities import PluginCapabilities, RuntimeDependency
    from omnidriver.core.contracts.dictionary import DictEntry
    from omnidriver.core.quantities.model import ArtifactValueReader
    from omnidriver.core.runtime.models import TutorialSpec, CaseConfig, DataArtifact
    from omnidriver.core.planning_types import StrictDiagnostic
    from omnidriver.core.tutorials_display import TutorialDisplay
    from omnidriver.core.plugin_capabilities import ResolvedInput
    from omnidriver.core.report_catalog import ReportDefinition
    from omnidriver.core.provider_identity import StackIdentity, ProviderIdentity
    from pathlib import Path


class CapabilityManifest(Protocol):
    """Protocol for a solver's capability manifest."""
    # This can be expanded based on the solver's specific domain (e.g. models, physics)
    pass


@runtime_checkable
class SolverPlugin(Protocol):
    """Strict contract implemented by an environment or solver adapter.

    Core owns workflow mechanics; the adapter owns runtime conventions and
    domain vocabulary. OpenFOAM and cardiacFOAM are concrete implementations,
    not requirements of this protocol.
    """
    
    @property
    def plugin_name(self) -> str:
        """Display name of the adapter or solver plugin."""
        ...

    @property
    def plugin_id(self) -> str:
        """Stable machine identifier, independent of the display name."""
        ...

    @property
    def plugin_version(self) -> str:
        """Version of the plugin semantics used to construct a plan."""
        ...

    @property
    def plugin_api_version(self) -> str:
        """Version of the omnidriver plugin contract implemented by this plugin."""
        ...

    # -- Command authorization -----------------------------------------------
    def get_solver_commands(self) -> frozenset[str]:
        """Binaries that produce a run's artifacts. Core's artifact-producer
        heuristic consults this set alone, never the auxiliary one."""
        ...

    def get_auxiliary_commands(self) -> frozenset[str]:
        """Additionally authorized binaries that produce no artifacts of their
        own -- meshers, decomposers, reconstructors."""
        ...

    def get_environment_commands(self) -> frozenset[str]:
        """Optional static commands supplied by the execution environment.

        An environment adapter declares its meshing, reconstruction, or other
        runtime tools here. Core does not provide environment command names.
        """
        ...

    def is_installed_environment_command(self, command: str) -> bool:
        """Optional runtime lookup for an environment-provided application."""
        ...

    def get_utility_manifests(self) -> dict[str, Any]:
        """Per-utility declarations of what each pre/post-solve utility
        consumes and produces, so workflow steps can be checked before they
        run."""
        ...

    def get_utility_roots(self) -> tuple["Path", ...]:
        """Directories holding this plugin's utility sources, for provenance
        fingerprinting."""
        ...

    # -- Case introspection ---------------------------------------------------
    def resolve_case_models(self, case_root: "Path") -> dict[str, Any]:
        """Best-effort read of a case's on-disk model selections. Must never
        raise: agents call it against partly-written cases."""
        ...

    def get_samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        """Fields the resolved model exposes for sampling by function objects,
        keyed by region."""
        ...

    # -- Configuration vocabulary --------------------------------------------
    def get_override_schema(
        self, tutorial_name: str, make_spec_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Machine-readable description of the ``--config`` JSON an agent may
        write for this tutorial, including a worked example."""
        ...

    def get_run_document_config_schema(self) -> dict[str, Any]:
        """JSON Schema for this plugin's RunDocument ``config`` object. Core
        validates against it dynamically and reports structured diagnostics,
        which is what lets an agent repair its own document."""
        ...

    def get_dict_entry_catalog(self) -> dict[str, Any]:
        """The plugin's dictionary entries arranged by its own document names,
        unserialized -- core owns serialization, the plugin owns vocabulary."""
        ...

    # -- Runtime evidence ------------------------------------------------------
    def get_solve_step_commands(self) -> frozenset[str]:
        """Which commands count as the solve step, for telemetry attribution."""
        ...

    def get_log_redaction_patterns(self) -> tuple[str, ...]:
        """Regular expressions whose matches are replaced in kept step logs
        (for example a credential a solver prints in its build header).

        Every match is replaced whole by ``[REDACTED]``; capture groups are
        not kept (clarified 2026-09-25, wave-2 review I3). Match only the
        secret, using lookarounds for any context it needs, e.g.
        ``(?<=://)[^/\\s@]+(?=@)`` for a URL's credential."""
        ...

    def get_telemetry_source_globs(self, command: str) -> tuple[str, ...]:
        """Where a given command writes the logs telemetry is parsed from."""
        ...

    def get_extra_provenance_paths(self, case_root: "Path") -> tuple["RuntimeDependency", ...]:
        """Run-time dependencies outside the case tree: the solver binary, a
        linked library, a case-local shared object.

        Returns ``RuntimeDependency`` rather than bare paths so that "required
        but not found" is expressible. A tuple of paths can only omit, and
        omission reads as "nothing to check" -- the gap that let a rebuilt
        solver replay a resumed run's numbers as fresh."""
        ...

    def get_artifact_value_reader(self, artifact_format: str) -> "ArtifactValueReader | None":
        """The reader for one of this plugin's artifact formats, or ``None``.
        Composed ``single`` (the most specific provider with a reader for the
        format answers). Contract: ``core.quantities.ArtifactValueReader``."""
        ...

    def get_profile(self):
        """Return declarative case/C++ provenance metadata for this plugin."""
        ...

    def get_capabilities(self) -> CapabilityManifest:
        """
        Return the capabilities of the solver (e.g., supported physics, 
        models, regions).
        """
        ...

    def get_tutorial_catalog(self) -> dict:
        """
        Return the tutorial specs provided by this solver.
        """
        ...

    def validate_configuration(self, spec: TutorialSpec) -> tuple[StrictDiagnostic, ...]:
        """
        Solver-specific validation logic that goes beyond simple DictEntry constraints.
        Returns a tuple of diagnostics (errors/warnings).
        """
        ...

    def validate_run_semantics(self, context: dict[str, Any]) -> tuple[StrictDiagnostic, ...]:
        """Return solver-specific validation errors for a flattened config."""
        ...

    def predict_data_artifacts(self, case_root: Path, spec: TutorialSpec) -> tuple[DataArtifact, ...]:
        """
        Predict the domain-specific artifacts (like ECGs or Purkinje VTK files) 
        that this solver expects to produce.
        """
        ...

@dataclass(frozen=True)
class PluginIdentity:
    """Stable description of the plugin semantics attached to an operation.

    **Superseded 2026-09-21.** :class:`DriverContext.identity` now holds a
    :class:`~omnidriver.core.provider_identity.StackIdentity` -- one identity
    per operation was an arity assumption that composition removes, the same
    way :class:`DriverContext.plugin` was. This class is kept, unconstructed
    by :func:`driver_context`, because nothing in this repository still names
    it; delete it once that stays true across a survey.
    """

    id: str
    version: str
    api_version: str
    source: str
    capability_digest: str

    def to_json(self) -> dict[str, str]:
        """Serialise this identity for provenance records and ``describe``."""
        return {
            "id": self.id,
            "version": self.version,
            "api_version": self.api_version,
            "source": self.source,
            "capability_digest": self.capability_digest,
        }


@dataclass(frozen=True)
class DriverContext:
    """Per-operation provider stack for solver-specific behaviour.

    Immutable and threaded through planning, discovery and execution, as
    before. What changed 2026-09-20 is arity: this held a single `plugin`
    because the migration it came from replaced a process-global active
    plugin, and that migration was about isolation, not about how many
    providers there are. Composition was consequently done by hand inside each
    solver plugin, differently in each.
    """

    providers: tuple[SolverPlugin, ...]
    identity: "StackIdentity"
    # The ``--plugin`` value that rebuilds this context in another process,
    # recorded where a selector becomes a context (``load_plugin_context``,
    # ``load_discovered_plugin``) and ``None`` everywhere else: a hand-built
    # or default context was produced by no selector, and inventing one would
    # be a guess. Added 2026-09-24: sweep_run's per-case ``python -m
    # omnidriver run`` child was never told which plugin its parent had, so
    # it resolved the entry-point default -- which refuses whenever two
    # solver-tier adapters are installed. Excluded from equality because it
    # says how to rebuild a context, not what the context is, and from
    # ``identity`` for the same reason ``ProviderIdentity.source`` is kept out
    # of ``capability_digest``.
    plugin_selector: str | None = field(default=None, compare=False)

    @cached_property
    def capabilities(self) -> "PluginCapabilities":
        """Return the focused internal view without changing dataclass fields."""
        from .provider_stack import compose

        return compose(self.providers)


@runtime_checkable
class SolverPluginOptionalHooks(Protocol):
    """Optional hooks a plugin MAY implement. Documentation, not enforcement.

    Every member here is probed with ``getattr`` by an adapter in
    :mod:`omnidriver.core.plugin_capabilities`. None is listed in
    ``_REQUIRED_PLUGIN_MEMBERS``, so this class is inert at load time:
    ``validate_plugin`` never consults it, and declaring or omitting any of
    these changes no plugin's loading behaviour.

    **Corrected 2026-09-20:** this previously also named
    ``_REQUIRED_V2_MEMBERS``, a constant that exists in no module -- it was
    referenced only here. It named two hook counts, 14 and fifteen, where the
    class declares neither.

    **Why this class exists.** Until it did, these hooks appeared
    nowhere in the plugin contract. They were reachable only by reading the
    private ``_*Adapter`` bodies, so a plugin author reading this file could
    not discover that the extension points existed at all -- while *not*
    implementing one silently routed them into a compatibility fallback.

    **Not implementing a hook is a real choice, not a no-op.** When the hook
    is absent, the adapter uses the named compatibility behavior documented in
    :mod:`omnidriver.core.compatibility`. These fallbacks are neutral or
    explicitly refuse unsupported operations; they do not infer a solver's
    vocabulary. A plugin that does not implement ``route_sweep_case_values``
    and ``materialize_sweep_case`` cannot be swept and is told so by name.

    Hooks are grouped by the capability they back; see that capability's
    docstring in ``plugin_capabilities.py`` for the full contract.
    """

    # -- CaseCompatibilityCapability -----------------------------------------
    def has_case_marker(self, case_root: "Path") -> bool:
        """Whether this case folder belongs to this plugin, by filesystem
        evidence alone. Absent -> ``False``."""
        ...

    def is_case_runnable_without_workflow(self, case_root: "Path") -> bool:
        """Whether a case without driver-owned workflow metadata is runnable.

        Absent -> ``False``; an adapter-declared entrypoint is checked
        separately by Core.
        """
        ...

    # -- RunDocumentConfigurationCapability ----------------------------------
    def build_run_document_config(
        self, spec: "TutorialSpec",
    ) -> tuple[dict[str, dict[str, Any]], tuple["StrictDiagnostic", ...]]:
        """Build this plugin's RunDocument ``config`` object and any
        diagnostics. Core imposes no key set (``schemas/run-document.json``
        declares ``config`` open). Absent -> ``({}, ())``."""
        ...

    # -- MeshDiagnosticPolicyCapability --------------------------------------
    def is_nondimensional_case(self, spec: "TutorialSpec") -> bool:
        """Whether SI mesh-scale diagnostics should be skipped for this case.
        Absent -> ``False``, keeping the diagnostics on."""
        ...

    def get_mesh_geometry_diagnostics(self, case_root: "Path") -> tuple[Any, ...]:
        """Plan-time geometry checks over plugin-owned point sets that are not
        polyMesh regions. Absent -> ``()``; there is no fallback, because "no
        extra checks" is correct for a plugin that has none."""
        ...

    def get_base_mesh_geometry_diagnostics(self, case_root: "Path") -> tuple[Any, ...]:
        """Base mesh-geometry classification supplied by the adapter.

        Absent -> no base geometry evidence is claimed.
        """
        ...

    # -- SweepMaterializerCapability -----------------------------------------
    def route_sweep_case_values(
        self,
        *,
        base: dict[str, Any],
        resolved_axis_values: dict[str, Any],
        driver_context: Any,
    ) -> dict[str, Any]:
        """Map one resolved sweep-axis combination onto this plugin's own
        case vocabulary. Must be pure -- no writes; ``materialize_sweep_case``
        does those. Absent -> sweeps are refused by name."""
        ...

    def materialize_sweep_case(self, *, case_dir: "Path", routed: dict[str, Any]) -> None:
        """Write one routed sweep case to disk. Absent -> sweeps are refused
        by name rather than materialized by another plugin's writer."""
        ...

    # -- CaseFileContractCapability ------------------------------------------
    def get_config_resolution_description(self) -> str:
        """One human-readable sentence naming which files resolve into a valid
        RunDocument config. Absent -> a plugin-neutral sentence."""
        ...

    # -- CaseRuntimeConventionsCapability ------------------------------------
    def get_case_runtime_conventions(self):
        """Declare generated case paths and an optional output collection
        root for this execution environment. Absent -> a neutral declaration
        that preserves authored paths and collects no convention-specific
        output."""
        ...

    # -- ConfigValueCapability ------------------------------------------------
    def get_config_value_reader(self):
        """Return a ``(path, key_path_tuple) -> value | None`` reader for
        this adapter's configuration format -- ``key_path_tuple`` is always
        a TUPLE (e.g. ``("bidomainSolverCoeffs", "conductivitySource")`` for
        a nested key, or a one-element tuple for a top-level one), never a
        single string; an adapter's own reader splits it into whatever
        scope/leaf-key shape its file format needs (see
        ``openfoam.environment._read_config_value_by_key_path`` for the
        reference split). Absent -> no format-specific reader."""
        ...

    # -- EnvironmentPreflightCapability -----------------------------------------
    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, environment_source=None, driver_context=None,
    ) -> tuple[Any, ...]:
        """Preflight the runtime environment a plan's workflow_dag will run
        in. Absent -> no adapter-specific environment evidence is claimed.
        ``environment_source`` is the operator's opaque ``--environment-source``
        value; this plugin decides what it means (renamed from
        ``explicit_bashrc`` 2026-09-26, spec A1)."""
        ...

    def get_configured_environment(self, env, driver_context) -> dict[str, str]:
        """Apply this adapter's environment contract to an already-sourced
        environment mapping. Absent -> the mapping is preserved unchanged."""
        ...

    # -- DictDiagnosticsCapability ---------------------------------------------
    def get_function_object_field_diagnostics(
        self, case_root: "Path", *, samplable: dict[str, Any],
    ) -> tuple[Any, ...]:
        """Warn about adapter-defined function objects sampling fields absent
        from ``samplable``. Absent -> no such diagnostics are emitted."""
        ...

    def get_case_dict_key_diagnostics(
        self, case_root: "Path", *, catalogued_paths, dict_relpaths: tuple[str, ...],
    ) -> tuple[Any, ...]:
        """Warn about dictionary keys absent from the plugin's catalogue.
        Absent -> no format-specific key diagnostics are emitted."""
        ...

    # -- CaseProvenanceCapability --------------------------------------------
    def get_required_inputs(
        self,
        case_root: "Path",
        resolved_case: dict[str, Any],
    ) -> tuple["ResolvedInput", ...]:
        """Already-resolved input paths this case reads. Resolved, not globs:
        field names are dictionary-configurable and locations resolve by a
        backward ``Time::findInstance`` search. Absent -> ``()``, which under
        the resolution precedence means "every unknown file is a required
        input" -- safe, but coarse."""
        ...

    def get_generated_output_globs(
        self,
        case_root: "Path",
        resolved_case: dict[str, Any],
    ) -> tuple[str, ...]:
        """Globs for files this case generates rather than consumes. Globs are
        fine here: generated diagnostics have fixed names. Absent -> ``()``."""
        ...

    def get_input_roots(
        self, case_root: "Path", resolved_case: dict[str, Any],
        *, conventions: Any,
    ) -> tuple[str, ...]:
        """Case-relative directories whose files a run reads as state, beyond
        the case-file roots: for example the directory a run resumes from,
        and that directory inside each parallel replica. Absent -> ``()``:
        core walks no state directory. Each must be a non-empty case-relative
        ``str`` path inside the case (added 2026-09-26, spec A2).

        ``conventions`` is the stack's merged ``CaseRuntimeConventions`` --
        the same value staging and discovery read -- so a plugin computing
        replica roots reads its own replica globs from there rather than a
        second, independent copy (R2 fix, finding I2)."""
        ...

    # -- EnvironmentPreflightCapability --------------------------------------
    def get_loaded_environment(
        self, *, environment_source: str | None, driver_context: Any,
    ) -> dict[str, str]:
        """Build the execution environment from scratch, e.g. by sourcing
        whatever ``environment_source`` names. Distinct from
        ``get_configured_environment``, which overlays a plugin contract onto
        an environment that already exists.

        Absent -> the current process environment is used unchanged."""
        ...

    # -- OverrideScopeCapability ---------------------------------------------
    def apply_overrides(
        self, overrides: Any, *, case_root: "Path", driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Validate and apply a ``--apply`` override document to a case.

        One call, not two: core has only ever validated and applied together,
        and separating them would let a caller apply without validating. Raise
        a ``ValueError`` subclass to reject. ``driver_context`` is the
        caller's context -- an adapter must thread it through, not build a
        substitute from itself, or it silently discards whatever solver
        semantics the caller carried.

        ``execution_env`` is the selected runtime's environment. When it is
        supplied the adapter MUST read each written value back under it and
        return one evidence record per override; returning ``()`` with an
        environment in hand is refused by the capability adapter, because "I
        wrote it and can say nothing about the result" is not a passed check.
        When it is absent the write still happens and the adapter reports
        whatever it can, which may be nothing. Absent -> applying overrides is
        unsupported for this adapter.

        Added 2026-09-22 (audit finding F1): the parameter existed on the
        capability adapter and was never forwarded here."""
        ...

    def get_override_target_paths(
        self, overrides: Any, *, case_root: "Path", driver_context: Any,
    ) -> tuple["Path", ...]:
        """Return every file ``apply_overrides`` may mutate, without writing.

        Required when a plugin supplies its own mutator so core can persist
        exact before-images before publishing an applying transaction.
        ``driver_context`` is the caller's context (see ``apply_overrides``)."""
        ...

    def inspect_effective_configuration(
        self, *, case_root: "Path", execution_env: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Read declared configuration dependencies without modifying a case.

        Records inspected and absent optional files, or explicitly reports an
        unresolved closure. Absent -> no format-specific configuration
        evidence is claimed.
        """
        ...

    # -- ReportCatalogCapability ---------------------------------------------
    def get_report_catalog(self) -> tuple["ReportDefinition", ...]:
        """Post-run reports this plugin offers. Core owns the machinery; the
        catalog itself is plugin data. Absent -> ``()``."""
        ...

    # -- NamedCatalogsCapability ---------------------------------------------
    def get_named_catalogs(self) -> dict[str, Any]:
        """Plugin-chosen catalogs, namespaced under ``plugin_catalogs`` in
        ``describe``. Core imposes no key set. Absent -> ``{}``."""
        ...

    # -- OverrideScopeCapability / DictRegenerationCapability ----------------
    def get_override_scopes(self) -> tuple[Any, ...]:
        """``$TOKEN.``-scoped override targets that patch a dict in place.
        Absent -> ``()``."""
        ...

    def get_regeneration_scopes(self) -> tuple[Any, ...]:
        """Bare selector overrides whose value change REGENERATES a dict file
        rather than patching it -- renaming sub-blocks or changing which
        sibling keys are legal. Absent -> ``()``."""
        ...

    # -- DictKeyScannerCapability ---------------------------------------------
    def get_dict_key_scanner(self):
        """Return a ``(source_root, *, allowlist_path, entries) -> report``
        callable that scans this adapter's C++ source for dictionary-key
        reads, for the strict-planning catalogue/C++ drift check. Absent ->
        the neutral scanner that reports no drift."""
        ...

    # -- TutorialRecordCapability ---------------------------------------------
    def get_tutorial_records(self) -> dict[str, Any]:
        """This plugin's tutorial records, keyed by name.

        A record (``core.tutorial_records.TutorialRecord``) is inert data --
        a native case path, its allowed axes, its workflow steps -- not a
        callable factory. Distinct from ``get_tutorial_catalog()``'s
        ``spec_factories``, which core calls; a record is core data core
        never calls into the plugin to build. Absent -> ``None``, not
        ``{}`` (review finding M1: distinct from a plugin that implements
        this hook and simply registers no records yet) -- the ordinary
        case for a plugin that has not migrated any tutorial onto this shape
        yet (design doc ``docs/superpowers/specs/2026-09-24-tutorials-are-
        pointers-design.md``)."""
        ...

    # -- AxisCapability --------------------------------------------------------
    def get_axis_catalog(self) -> dict[str, Any]:
        """This plugin's named axes, keyed by name.

        An axis (``core.tutorial_records.AxisContract``) is a name, the value
        kind it accepts, and a pure function ``(value, staged_case_root) ->
        AxisResult``. Core defines the contract and ships none itself. Absent
        -> ``None``, not ``{}`` (review finding M1) -- callers treat that the
        same as an empty catalog either way: a study naming a bare axis this
        plugin does not provide is refused by name, same as one it never
        declared."""
        ...

    # -- RecordKeyValidationCapability ------------------------------------------
    def get_record_key_validator(self):
        """Return a ``(document, key_path, value) -> (value_kind, validated)``
        callable that checks a tutorial-record study's direct ``document:key``
        name against this plugin's own dictionary catalog.

        Raises ``KeyError`` (or any exception) for a name the catalog does
        not recognise -- refusing it is this hook's own choice (design §5: "a
        [solver]-owned key absent from the catalog... never bypassed"); an
        adapter that instead wants to accept an undeclared key unchecked (the
        environment-owned-key exception, a key some underlying format reads
        but this plugin has no full catalog for yet) returns
        ``(inferred_kind, False)`` rather than raising -- both are
        legitimate, adapter-owned answers core does not choose between.
        Absent -> ``None`` (review finding M1): a stack with no validator
        REFUSES a record case outright (``record_execution
        ._resolve_and_split``) rather than checking no direct key at all."""
        ...

    # -- CaseValueComparisonCapability -------------------------------------------
    def get_case_value_comparator(self):
        """Return a ``(value_kind, requested, current) -> bool`` callable, or
        ``None``.

        Typed comparison: a requested ``"1e-3"`` and a case's resolved
        ``"0.001"`` are ``False`` under Python ``==`` but the same value in
        every dictionary format this framework writes, so a tutorial-record
        patch's "is this unchanged" check (``core.tutorial_records``) must
        never fall back to string or Python ``==`` equality. Absent ->
        ``None`` (review finding M1): a stack with no comparator REFUSES a
        record case outright rather than reporting every patch "changed" and
        committing it."""
        ...

    # -- RecordSurfaceCapability (C10) ------------------------------------------
    def get_record_key_catalog(self, case_root: "Path") -> tuple[Mapping[str, Any], ...]:
        """Every key a study may name for this case: document, key, value_kind, and optionally
        default/description/minimum/maximum/menu. Indexed keys may use ``[Int]`` for any index.

        ``[Int]`` is generic index notation, not a solver's syntax: a key
        whose path segment carries a concrete index (``stim[0].start``) is
        matched against its template (``stim[Int].start``). Absent -> no
        keys, which the conformance check C10 reports as a failure."""
        ...

    def get_agent_guidance(self) -> tuple[Mapping[str, str], ...]:
        """Solver-level advice an agent should read before writing a study (title, text).
        Absent -> none, which C10 reports as a failure."""
        ...

    # -- DictionaryCatalogCapability ------------------------------------------
    def get_phases(self) -> tuple[str, ...]:
        """This plugin's dictionary editing phases, in order.

        The ORDER is the semantics, not decoration: ``primary_phase()`` returns
        the first phase in this tuple that an entry claims, and every other
        phase the entry declares is a read-only mirror. These strings are also
        the top-level keys of ``RunDocument.config``.

        Absent -> the phases the plugin's own ``DictEntry`` values declare,
        which is correct but unordered. Declare this hook if any entry is
        multi-phase, because otherwise which phase is "primary" is arbitrary."""
        ...

    # -- CaseWriterCapability -------------------------------------------------
    def resolve_case_mutation(
        self, request: Any, *, driver_context: Any,
    ) -> Any:
        """Resolve a mutation request into concrete addresses and effects.

        The semantic owner's hook: which parameters apply, what they mean,
        which document and key each lands in, and what the edit is expected to
        change. Returns a ``ResolvedMutation``.

        **Pure.** Must not read or write the filesystem. A dry run's promise of
        costing nothing rests on this, and core enforces it rather than
        trusting it -- but only as far as that enforcement actually reaches
        (**narrowed 2026-09-23, R2 finding 12**): what is enforced is that no
        path is added or removed under ``request.case_root`` by name, between
        two snapshots taken before and after this hook runs. In-place content
        or permission changes, a write outside ``request.case_root``, a
        create-then-delete of one path within the call, and -- the one that
        matters most -- any READ at all, are none of them caught. A resolver
        that reads makes the dry run's answer depend on case state at read
        time, which defeats the entire reason this hook is declared pure; the
        enforcement above will not tell you this happened. Raise a
        ``ValueError`` naming the supported modes to refuse a mode this
        adapter does not support. Absent -> this adapter authors no case
        inputs."""
        ...

    def get_supported_mutation_modes(self) -> "frozenset[str]":
        """Which creation modes this adapter supports.

        Adapters differ and are meant to: cardiacCore preprocessing patches
        declared dictionaries, cardiacFoam synthesizes a case from a catalog.

        **Corrected 2026-09-23 (R2 finding 0):** this used to say "Absent ->
        every mode the adapter's ``resolve_case_mutation`` accepts" -- a
        promise core cannot keep, since nothing here introspects what a
        resolver hook accepts, and it was the root cause of three installed
        providers, implementing no resolver either, reporting support for
        every mode. Absent alongside ``resolve_case_mutation`` -> refused by
        name (an implemented resolver whose supported modes are undeclared).
        Absent alongside no ``resolve_case_mutation`` -> no modes."""
        ...

    def get_rendered_formats(self) -> "frozenset[str]":
        """File formats this provider renders. Exactly one declarer per format.

        Composition refuses a stack where two providers claim one format: the
        bytes reaching disk would otherwise depend on composition order.
        Absent -> this provider renders nothing."""
        ...

    def render_case_files(
        self, resolved: Any, *, snapshot_root: "Path", driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        """Render complete proposed file contents, in this provider's formats.

        The format owner's hook. **Reads** the case -- it must, to patch an
        existing file -- and writes nothing outside ``snapshot_root``, an
        isolated copy core provides. Returns ``RenderedFile`` objects with
        complete bytes; core commits them and this hook does not.

        ``execution_env`` is the selected runtime, for a renderer that must
        resolve includes or evaluate a directive to know what it is editing.
        Declare every file read through it as a precondition on the
        ``ResolvedMutation``, including files that were *absent* where their
        presence would change which file is selected. Absent -> this provider
        renders nothing."""
        ...

    # -- DictionaryCatalogCapability / TutorialCatalogCapability ----------------
    # Optional-neutral since 2026-09-26 (spec 2026-09-26 A3).
    def get_dict_entries(self) -> tuple[DictEntry, ...]:
        """The plugin's dictionary entries. Absent -> ``()``; the identity
        digest then hashes ``()``, exactly as an empty stub did."""
        ...

    def get_dictionary_catalog(self):
        """Entries partitioned by plugin-owned document name. Absent -> an
        empty ``DictionaryCatalog``."""
        ...

    def get_dict_groups(self) -> dict[str, tuple[DictEntry, ...]]:
        """Entries by the plugin's own group names. Absent -> ``{}``."""
        ...

    def get_tutorial_displays(self) -> tuple[TutorialDisplay, ...]:
        """Display cards for the registered tutorials. Absent -> ``()``."""
        ...


# The single plugin contract version this core can drive. Anything else is
# refused before any plugin catalog code runs.
SUPPORTED_PLUGIN_API_VERSIONS: frozenset[str] = frozenset({"2"})


#: Identity properties, which are strings rather than capability members and
#: therefore appear in no capability's ``:adapts:`` list.
_IDENTITY_MEMBERS = (
    "plugin_name",
    "plugin_id",
    "plugin_version",
    "plugin_api_version",
)


def _required_plugin_members() -> tuple[str, ...]:
    """The contract members ``validate_plugin`` rejects a plugin for lacking.

    Derived from the capability seams' ``:status:`` tiers rather than
    hand-maintained beside them. Before 2026-09-20 these were two independent
    lists and they disagreed: the tuple named 27 members while the
    ``SolverPlugin`` Protocol declared 29, and the two it omitted were exactly
    the environment ones.
    """
    from .capability_seams import members_by_tier

    return _IDENTITY_MEMBERS + tuple(sorted(members_by_tier()["required"]))


_REQUIRED_PLUGIN_MEMBERS = _required_plugin_members()

_PLUGIN_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


def validate_plugin(plugin: Any) -> SolverPlugin:
    """Reject malformed plugin objects before they enter a driver context.

    This is an interface guard, not a sandbox: an imported plugin is trusted
    in-process Python code.  Methods are checked structurally here; their
    returned values are validated by their owning core consumers.
    """

    missing = [name for name in _REQUIRED_PLUGIN_MEMBERS if not hasattr(plugin, name)]
    if missing:
        raise TypeError(
            "SolverPlugin is missing required members: " + ", ".join(sorted(missing))
        )
    for name in ("plugin_name", "plugin_id", "plugin_version", "plugin_api_version"):
        value = getattr(plugin, name)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"SolverPlugin.{name} must be a non-empty string")
    # Refused here -- before the callable checks, before get_profile(), and
    # before any catalog member -- so an unsupported plugin's catalog code
    # never executes.
    if plugin.plugin_api_version not in SUPPORTED_PLUGIN_API_VERSIONS:
        raise TypeError(
            f"SolverPlugin.plugin_api_version {plugin.plugin_api_version!r} is "
            "not supported; this omnidriver core drives "
            f"{sorted(SUPPORTED_PLUGIN_API_VERSIONS)}"
        )
    if not _PLUGIN_ID_RE.fullmatch(plugin.plugin_id):
        raise TypeError(
            "SolverPlugin.plugin_id must use lowercase letters, digits, dots, "
            "or hyphens and cannot start or end with punctuation"
        )
    # A member's presence is not enough -- it must be callable. Collected as
    # one batch rather than raised on the first miss, so a partial
    # implementation is reported completely instead of one name at a time.
    non_callable = [
        name for name in _REQUIRED_PLUGIN_MEMBERS
        if name not in ("plugin_name", "plugin_id", "plugin_version", "plugin_api_version")
        and not callable(getattr(plugin, name, None))
    ]
    if non_callable:
        raise TypeError(
            "SolverPlugin does not implement the plugin contract; missing: "
            + ", ".join(sorted(non_callable))
        )
    return plugin


def _declared_dict_entries(provider: Any) -> tuple[Any, ...]:
    """A provider's dictionary entries, or ``()`` when it declares none.

    ``()`` is the identity digest's input for "none" (spec 2026-09-26 A3).
    A provider without ``get_dict_entries`` digests exactly as one whose
    stub returned ``()`` did, so deleting such a stub changes no provider
    digest."""
    hook = getattr(provider, "get_dict_entries", None)
    return tuple(hook()) if callable(hook) else ()


def _validate_one_provider(provider: SolverPlugin) -> SolverPlugin:
    """Structural checks a single provider must pass before it joins a stack.

    Each check here was previously run once, against the single plugin a
    context held. Composition does not relax any of them -- a provider that
    fails one of these is malformed regardless of what else is in its stack,
    so each provider is still checked independently rather than only as part
    of the composed whole.
    """

    checked = validate_plugin(provider)
    profile = checked.get_profile()
    if profile.plugin_id != checked.plugin_id:
        raise TypeError("SolverPlugin profile id does not match plugin_id")
    if profile.api_version != checked.plugin_api_version:
        raise TypeError("SolverPlugin profile API version does not match plugin_api_version")

    from .contracts.dictionary import DictEntry

    entries = _declared_dict_entries(checked)
    invalid_entries = [
        entry for entry in entries
        if not isinstance(entry, DictEntry) or not entry.driver_path.strip()
    ]
    if invalid_entries:
        raise TypeError("SolverPlugin.get_dict_entries() must return DictEntry values with paths")
    paths = [entry.driver_path for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise TypeError(
            "SolverPlugin dictionary catalog has duplicate paths: "
            + ", ".join(duplicates)
        )

    from .provider_stack import check_provides

    problems = check_provides(checked)
    if problems:
        raise TypeError("; ".join(problems))

    return checked


def _provider_identity(provider: SolverPlugin, *, source: str) -> "ProviderIdentity":
    """One provider's own identity, independent of the stack it joins."""
    from .provider_identity import ProviderIdentity

    provider_digest = _resolved_capability_digest(
        profile_digest=provider.get_profile().digest,
        dictionary_entries=_declared_dict_entries(provider),
        manifest=provider.get_capabilities(),
    )
    return ProviderIdentity(
        id=provider.plugin_id,
        version=provider.plugin_version,
        api_version=provider.plugin_api_version,
        source=source,
        provider_digest=provider_digest,
    )


def driver_context(
    *providers: SolverPlugin,
    source: str | Sequence[str],
    plugin_selector: str | None = None,
) -> DriverContext:
    """Create a validated immutable context for an ordered provider stack.

    One provider is the common case -- a solver plugin on its own -- but any
    number may be supplied, e.g. a solver plugin layered on the environment
    adapter it requires. Each provider is validated and profile-checked
    independently; the stack is then ordered least-specific first by
    :func:`provider_stack.order_providers` and composed eagerly so that a
    packaging error (a duplicated case-file declarer, two providers claiming
    the same exclusive hook, ...) is raised here rather than lazily, the
    first time some caller happens to touch ``.capabilities``.

    ``source`` is a single string, broadcast to every provider -- the
    overwhelmingly common single-provider call shape, and still correct for
    several providers that genuinely share one origin (e.g. all loaded from
    the same trusted local import) -- or one string per provider, positional
    against ``providers`` as given (not against the reordered stack; pairing
    is tracked by ``plugin_id`` internally, so which position wins the
    reorder does not matter). A shared string for a multi-provider stack
    whose providers do NOT share an origin silently records the wrong
    provenance for every provider but one -- that was
    :func:`~omnidriver.core.plugin_discovery.default_discovered_context`'s
    bug before it started passing one source per provider explicitly.

    ``plugin_selector`` is passed only by the loaders that turn a ``--plugin``
    value into a context; see :attr:`DriverContext.plugin_selector`.
    """

    if not providers:
        raise TypeError("driver_context() requires at least one provider")

    if isinstance(source, str):
        sources = (source,) * len(providers)
    else:
        sources = tuple(source)
        if len(sources) != len(providers):
            raise TypeError(
                f"driver_context() received {len(providers)} provider(s) but "
                f"{len(sources)} source(s); pass one string (shared by every "
                "provider) or exactly one source per provider"
            )

    from .provider_stack import order_providers, resolutions
    from .provider_identity import build_stack_identity

    checked_providers = tuple(_validate_one_provider(provider) for provider in providers)
    # Paired with the CHECKED providers, in the caller's original order --
    # before order_providers can reorder them. Looked back up by plugin_id
    # below, not position, so the pairing survives the reorder.
    source_by_id = dict(zip((p.plugin_id for p in checked_providers), sources))
    ordered = order_providers(checked_providers)

    provider_identities = tuple(
        _provider_identity(provider, source=source_by_id[provider.plugin_id])
        for provider in ordered
    )
    identity = build_stack_identity(
        providers=provider_identities,
        resolutions=resolutions(ordered),
    )
    context = DriverContext(
        providers=ordered, identity=identity, plugin_selector=plugin_selector,
    )
    # Eager, not lazy: touching .capabilities here runs provider_stack.compose
    # now, at construction, so a packaging error (the single-declarer rule
    # over case_files, two providers claiming the same exclusive hook, ...)
    # is raised here rather than lazily on whichever caller first reaches for
    # .capabilities. Because .capabilities is a cached_property, this is the
    # ONE compose() call for this context's lifetime, not a duplicate of a
    # later one -- the result is cached on the instance and every later
    # access (including this function's own callers) reuses it.
    context.capabilities
    return context


def _identity_jsonable(value: Any) -> Any:
    """Convert declarative capability data into deterministic digest input."""
    if is_dataclass(value):
        return _identity_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _identity_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_identity_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_identity_jsonable(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        "Plugin capability data must be deterministically serializable; got "
        f"{type(value).__name__}"
    )


def _resolved_capability_digest(
    *, profile_digest: str, dictionary_entries: tuple[Any, ...], manifest: Any,
) -> str:
    """Bind the profile, accepted dictionary vocabulary and manifest together."""
    payload = _identity_jsonable({
        "profile_digest": profile_digest,
        "dictionary_entries": dictionary_entries,
        "manifest": manifest,
    })
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_plugin_context(target: str) -> DriverContext:
    """Load a plugin by discovered id, or by trusted ``module:Class`` import.

    A colon always means the trusted local-development import form, which the
    CLI labels unsafe. Without a colon the argument names an installed plugin
    from the ``omnidriver.plugins`` entry-point group. Neither form is
    sandboxed: loading a plugin executes its Python code.
    """

    if ":" not in target:
        from .plugin_discovery import load_discovered_plugin

        return load_discovered_plugin(target)

    try:
        module_path, class_name = target.split(":", maxsplit=1)
        if not module_path or not class_name:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Plugin target must use the form 'module.path:ClassName'") from exc
    module = import_module(module_path)
    plugin_class = getattr(module, class_name)
    from .plugin_discovery import _expand_with_requirements

    providers, sources = _expand_with_requirements(
        plugin_class(), f"trusted-import:{target}",
    )
    return driver_context(*providers, source=sources, plugin_selector=target)


def default_driver_context() -> DriverContext:
    """Return a fresh compatibility context for the installed adapter set.

    This function exists at public compatibility boundaries only. Core
    internals must receive a :class:`DriverContext` explicitly and must not
    retain it in module state. With no adapter, or with multiple adapters,
    context creation raises rather than inventing a solver context.
    """

    from .compatibility import legacy_default_driver_context

    return legacy_default_driver_context()
