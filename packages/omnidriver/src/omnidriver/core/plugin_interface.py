"""The solver plugin contract.

A provider must have only its identity. Every other member of
:class:`SolverPlugin` is optional: ``provider_stack.MEMBERS`` says how a
stack composes it and what the stack answers when no provider implements it,
refusing by name where an operation needs it. See ``AGENT_GUIDE.md``,
"Adding a New Solver".
"""

# Annotations below name types imported only under TYPE_CHECKING; without
# lazy annotations, importing this module raises NameError before Python 3.14.
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from functools import cached_property
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry
    from omnidriver.core.planning_types import StrictDiagnostic
    from omnidriver.core.provider_identity import ProviderIdentity, StackIdentity
    from omnidriver.core.provider_stack import ProviderStack
    from omnidriver.core.quantities.model import ArtifactValueReader
    from omnidriver.core.repository import Repository
    from omnidriver.core.runtime.models import DataArtifact, TutorialSpec


@dataclass(frozen=True)
class RuntimeDependency:
    """Something a run's executable consumes outside the case tree: the
    solver binary, a library it loads, a case-local shared object. ``path``
    ``None`` on a required dependency is reported ``unavailable``."""

    name: str
    path: Path | None
    required: bool


@dataclass(frozen=True)
class CaseRuntimeConventions:
    """The paths an environment generates while a case runs.

    Core copies, snapshots and cleans cases; the names are the environment's.
    The empty declaration removes no authored path from a staged case.
    """

    generated_directory_names: tuple[str, ...] = ()
    generated_file_names: tuple[str, ...] = ()
    generated_file_prefixes: tuple[str, ...] = ()
    generated_file_suffixes: tuple[str, ...] = ()
    preserved_file_suffixes: tuple[str, ...] = ()
    generated_case_markers: tuple[str, ...] = ()
    case_entrypoints: tuple[str, ...] = ()
    case_script_commands: tuple[str, ...] = ()
    #: fnmatch globs naming a directory, at any depth, that holds one replica
    #: of the case per parallel rank (OpenFOAM: ``processor*``).
    replica_directory_globs: tuple[str, ...] = ()
    #: Regex a file or directory name matches when it is one of the solver's
    #: output instances (OpenFOAM: a time directory); ``None`` declares none.
    instance_directory_pattern: str | None = None
    #: Instance names that are authored input and never cleaned (OpenFOAM: ``"0"``).
    preserved_instance_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A bare str here would explode into one-character names under tuple().
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


def _require_tuple_of_names(conventions: CaseRuntimeConventions, field_name: str, *, noun: str) -> None:
    value = getattr(conventions, field_name)
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple of {noun}, got {type(value).__name__} {value!r}")
    for item in value:
        if not isinstance(item, str) or not item:
            raise TypeError(
                f"{field_name} must be a tuple of {noun}, got "
                f"{type(item).__name__} {item!r} among its items"
            )


class SolverPlugin(Protocol):
    """Every member a provider may implement. Only the four identity
    properties are required; each other member is composed and defaulted by
    ``provider_stack.MEMBERS``, which also names the operations that refuse
    without it."""

    plugin_name: str
    plugin_id: str
    plugin_version: str
    plugin_api_version: str

    # -- declarations ---------------------------------------------------------
    def get_profile(self):
        """The declarative profile (``plugin_profile.load_plugin_profile``):
        case files, C++ mapping, environment connection, ``requires``."""

    def get_capabilities(self) -> dict[str, Any]:
        """Domain entries core adds to the capability manifest as given."""

    def get_named_catalogs(self) -> dict[str, Any]:
        """Catalogs ``describe`` namespaces under ``plugin_catalogs``."""

    # -- dictionary vocabulary --------------------------------------------------
    def get_dict_entries(self) -> tuple["DictEntry", ...]:
        """Every dictionary entry this provider catalogues."""

    def get_dictionary_catalog(self):
        """The same entries as a ``DictionaryCatalog``, by document name."""

    def get_dict_groups(self) -> dict[str, tuple["DictEntry", ...]]:
        """The entries by this provider's own group names."""

    def get_dict_entry_catalog(self) -> dict[str, Any]:
        """The entries arranged by document name, unserialized."""

    def get_dict_key_scanner(self):
        """A ``(source_root, *, allowlist_path, entries, cache_root, force) ->
        report`` callable comparing the catalogue with the solver's C++; the
        report's ``to_json()`` has ``disagreements``, ``unread``,
        ``uncatalogued``, ``unresolved`` and ``selector_values``."""

    # -- commands -------------------------------------------------------------
    def get_solver_commands(self) -> frozenset[str]:
        """Binaries that produce a run's artifacts."""

    def get_auxiliary_commands(self) -> frozenset[str]:
        """Authorized binaries that produce no artifacts of their own."""

    def get_environment_commands(self) -> frozenset[str]:
        """Static commands the execution environment supplies."""

    def is_installed_environment_command(self, command: str) -> bool:
        """Whether ``command`` is an application the environment has installed."""

    def get_utility_manifests(self) -> dict[str, Any]:
        """``UtilityManifest`` per utility command: what it consumes and produces."""

    def get_solve_step_commands(self) -> frozenset[str]:
        """The commands that run the solve step, the one a parallel run rewrites."""

    # -- planning and validation ----------------------------------------------
    def validate_configuration(self, spec: "TutorialSpec") -> tuple["StrictDiagnostic", ...]:
        """What this provider objects to in a resolved spec."""

    def validate_run_semantics(self, case_root: Path) -> tuple["StrictDiagnostic", ...]:
        """The rules the resolved case at ``case_root`` breaks; an error
        refuses the record case before anything runs."""

    def predict_data_artifacts(self, case_root: Path, spec: "TutorialSpec") -> tuple["DataArtifact", ...]:
        """Files the case will produce; a missing one fails the run. Never raises."""

    def get_plan_diagnostics(
        self, case_root: Path, *, workflow_dag: dict[str, Any] | None, env: Mapping[str, str],
        scratch_root: Path | None, driver_context: Any,
    ) -> tuple["StrictDiagnostic", ...]:
        """What a strict plan adds about the case or the solver's source. An
        error fails the plan; ``scratch_root`` is where derived work may be cached."""

    def explain_step_failure(self, log_text: str, case_root: Path, *, driver_context: Any) -> tuple["StrictDiagnostic", ...]:
        """What a failed step's log tail says that its exit code does not."""

    def inspect_effective_configuration(
        self, *, case_root: Path, execution_env: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """The files the case's configuration resolves to, read without running."""

    # -- environment ----------------------------------------------------------
    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, environment_source=None, driver_context=None,
    ) -> tuple["StrictDiagnostic", ...]:
        """Preflight of the environment a plan will run in.
        ``environment_source`` is the operator's opaque ``--environment-source``."""

    def get_loaded_environment(self, *, environment_source: str | None, driver_context: Any) -> dict[str, str]:
        """The execution environment built from scratch, e.g. by sourcing
        ``environment_source``."""

    def get_configured_environment(self, env: dict[str, str], driver_context: Any) -> dict[str, str]:
        """This provider's contract applied over an existing environment."""

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        """The paths this environment generates in a case."""

    # -- provenance -----------------------------------------------------------
    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        """Best-effort model selections the case holds. Never raises."""

    def get_samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        """Fields the resolved model exposes for sampling, by region."""

    def get_generated_output_globs(self, case_root: Path, resolved_case: dict[str, Any]) -> tuple[str, ...]:
        """Globs for files the case generates rather than consumes; every
        other unknown file is a required input."""

    def get_input_roots(
        self, case_root: Path, resolved_case: dict[str, Any], *, conventions: CaseRuntimeConventions,
    ) -> tuple[str, ...]:
        """Case-relative directories a run reads as state (the instance it
        resumes from); ``conventions`` is the stack's merged declaration."""

    def get_extra_provenance_paths(self, case_root: Path) -> tuple[RuntimeDependency, ...]:
        """Run-time dependencies outside the case tree."""

    def get_log_redaction_patterns(self) -> frozenset[str]:
        """Regexes whose every match in a kept step log becomes ``[REDACTED]``."""

    def get_artifact_value_reader(self, artifact_format: str) -> "ArtifactValueReader | None":
        """The reader for one artifact format, or ``None``."""

    # -- records --------------------------------------------------------------
    def get_tutorial_records(self) -> dict[str, Any]:
        """``TutorialRecord`` values by name."""

    def get_record_key_catalog(self, case_root: Path) -> tuple[Mapping[str, Any], ...]:
        """Every key a study may name for this case: ``document``, ``key``,
        ``value_kind`` and optionally ``default``, ``description``,
        ``minimum``, ``maximum``, ``menu``. The key grammar (``[Int]``,
        ``<name>``) is ``runtime.record_surface``'s. A document written as
        asked without a catalogue is listed once with key ``"<any>"`` and
        ``validated: False``."""

    def get_agent_guidance(self) -> tuple[Mapping[str, str], ...]:
        """Advice an agent reads before writing a study: ``title``, ``text``."""

    def get_record_key_validator(self):
        """A ``(document, key_path, value) -> (value_kind, validated)``
        callable; it raises for a key it refuses."""

    def get_case_value_comparator(self):
        """A ``(value_kind, requested, current) -> bool`` typed comparison."""

    def get_config_value_reader(self):
        """A ``(path, key_path_tuple) -> value | None`` reader of this format."""

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        """The steps replacing one serial solve step for a parallel run.
        Exactly one keeps ``step["id"]`` and its ``produces``; the first
        follows ``step["depends_on"]``. Raises ``ValueError`` to refuse."""

    # -- case writing ---------------------------------------------------------
    def resolve_case_mutation(self, request: Any, *, driver_context: Any) -> Any:
        """A ``ResolvedMutation`` for the request. Pure: reads and writes
        nothing; core refuses one that changes the case tree."""

    def get_supported_mutation_modes(self) -> frozenset[str]:
        """The creation modes ``resolve_case_mutation`` accepts."""

    def render_case_files(
        self, resolved: Any, *, snapshot_root: Path, driver_context: Any, execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        """``RenderedFile`` values with complete bytes, in this provider's
        formats, reading the case copy at ``snapshot_root``."""

    def get_rendered_formats(self) -> frozenset[str]:
        """The file formats this provider renders; one renderer per format."""


IDENTITY_MEMBERS = ("plugin_name", "plugin_id", "plugin_version", "plugin_api_version")

#: The plugin contract versions this core drives.
SUPPORTED_PLUGIN_API_VERSIONS: frozenset[str] = frozenset({"2"})

_PLUGIN_ID_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


@dataclass(frozen=True)
class DriverContext:
    """The provider stack one operation runs against, threaded through
    planning, discovery and execution."""

    providers: tuple[SolverPlugin, ...]
    identity: "StackIdentity"
    #: The ``--plugin`` value that rebuilds this context in another process,
    #: or ``None`` for a context no selector produced. Not part of equality:
    #: it says how to rebuild a context, not what the context is.
    plugin_selector: str | None = field(default=None, compare=False)
    #: The solver repository the stack was selected from, or ``None``: its
    #: scripts folder serves a step that names a script, and a child process
    #: is given its root (``--repo``). Not part of equality, for the same reason.
    repository: Repository | None = field(default=None, compare=False)

    @cached_property
    def stack(self) -> "ProviderStack":
        from .provider_stack import ProviderStack

        return ProviderStack(self.providers)


def validate_plugin(plugin: Any) -> SolverPlugin:
    """Refuse a malformed provider before it joins a stack.

    An interface guard, not a sandbox: a plugin is trusted in-process code.
    """
    missing = [name for name in IDENTITY_MEMBERS if not hasattr(plugin, name)]
    if missing:
        raise TypeError("SolverPlugin is missing required members: " + ", ".join(sorted(missing)))
    for name in IDENTITY_MEMBERS:
        value = getattr(plugin, name)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"SolverPlugin.{name} must be a non-empty string")
    # Before any other member runs, so an unsupported plugin's code never executes.
    if plugin.plugin_api_version not in SUPPORTED_PLUGIN_API_VERSIONS:
        raise TypeError(
            f"SolverPlugin.plugin_api_version {plugin.plugin_api_version!r} is "
            f"not supported; this omnidriver core drives {sorted(SUPPORTED_PLUGIN_API_VERSIONS)}"
        )
    if not _PLUGIN_ID_RE.fullmatch(plugin.plugin_id):
        raise TypeError(
            "SolverPlugin.plugin_id must use lowercase letters, digits, dots, "
            "or hyphens and cannot start or end with punctuation"
        )
    from .provider_stack import check_provider_members

    problems = check_provider_members(plugin)
    if problems:
        raise TypeError(f"SolverPlugin {plugin.plugin_id!r}: " + "; ".join(problems))
    return plugin


def _declared_dict_entries(provider: Any) -> tuple[Any, ...]:
    hook = getattr(provider, "get_dict_entries", None)
    return tuple(hook()) if callable(hook) else ()


def _validate_one_provider(provider: Any) -> SolverPlugin:
    from .contracts.dictionary import DictEntry
    from .provider_stack import provider_profile

    checked = validate_plugin(provider)
    profile = provider_profile(checked)
    if profile.plugin_id != checked.plugin_id:
        raise TypeError("SolverPlugin profile id does not match plugin_id")
    if profile.api_version != checked.plugin_api_version:
        raise TypeError("SolverPlugin profile API version does not match plugin_api_version")
    entries = _declared_dict_entries(checked)
    if any(not isinstance(entry, DictEntry) or not entry.driver_path.strip() for entry in entries):
        raise TypeError("SolverPlugin.get_dict_entries() must return DictEntry values with paths")
    paths = [entry.driver_path for entry in entries]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    if duplicates:
        raise TypeError("SolverPlugin dictionary catalog has duplicate paths: " + ", ".join(duplicates))
    return checked


def _provider_identity(provider: SolverPlugin, *, source: str) -> "ProviderIdentity":
    from .provider_identity import ProviderIdentity
    from .provider_stack import provider_profile

    manifest = getattr(provider, "get_capabilities", None)
    payload = identity_jsonable({
        "profile_digest": provider_profile(provider).digest,
        "dictionary_entries": _declared_dict_entries(provider),
        "manifest": manifest() if callable(manifest) else {},
    })
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return ProviderIdentity(
        id=provider.plugin_id,
        version=provider.plugin_version,
        api_version=provider.plugin_api_version,
        source=source,
        provider_digest="sha256:" + hashlib.sha256(encoded).hexdigest(),
    )


def driver_context(
    *providers: SolverPlugin,
    source: str | Sequence[str],
    plugin_selector: str | None = None,
) -> DriverContext:
    """A validated, immutable context over an ordered provider stack.

    Each provider is validated on its own; the stack is ordered least
    specific first by ``requires`` and built eagerly, so a packaging error (a
    case file or format with two declarers) is raised here. ``source`` is one
    string shared by every provider, or one per provider in the order given.
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

    from .provider_identity import build_stack_identity
    from .provider_stack import ProviderStack, order_providers, resolutions

    checked = tuple(_validate_one_provider(provider) for provider in providers)
    source_by_id = dict(zip((p.plugin_id for p in checked), sources))
    ordered = order_providers(checked)
    stack = ProviderStack(ordered)
    identity = build_stack_identity(
        providers=tuple(_provider_identity(p, source=source_by_id[p.plugin_id]) for p in ordered),
        resolutions=resolutions(stack),
    )
    context = DriverContext(providers=ordered, identity=identity, plugin_selector=plugin_selector)
    context.__dict__["stack"] = stack
    return context


def identity_jsonable(value: Any) -> Any:
    """Declarative capability data as deterministic digest input."""
    if is_dataclass(value):
        return identity_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): identity_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [identity_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(identity_jsonable(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        "Plugin capability data must be deterministically serializable; got "
        f"{type(value).__name__}"
    )


def load_plugin_context(target: str) -> DriverContext:
    """Load a plugin by discovered id, or by trusted ``module:Class`` import.

    A colon means the trusted local-development import form, which the CLI
    labels unsafe; otherwise the argument names an installed plugin from the
    ``omnidriver.plugins`` entry-point group. Neither form is sandboxed.
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
    plugin_class = getattr(import_module(module_path), class_name)
    from .plugin_discovery import _expand_with_requirements

    providers, sources = _expand_with_requirements(plugin_class(), f"trusted-import:{target}")
    return driver_context(*providers, source=sources, plugin_selector=target)
