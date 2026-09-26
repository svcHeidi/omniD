"""Named Plan-1 compatibility boundaries.

These adapters intentionally preserve observable behavior.  They produce no
warnings and make no policy changes.  Keeping them named and documented stops
legacy decisions from being rediscovered deep inside solver-neutral code and
gives Plan 2 explicit seams at which behaviour may later change.
"""

from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_interface import DriverContext

_fallback_call_log: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_fallback_call_log", default=None,
)


@contextmanager
def track_fallback_calls():
    """Yield a list that fills with the name of every legacy_* fallback
    invoked inside the ``with`` block, in call order. Empty means none fired
    -- the P2.4 assertion an explicit non-cardiac v2 context should satisfy."""
    token = _fallback_call_log.set([])
    try:
        yield _fallback_call_log.get()
    finally:
        _fallback_call_log.reset(token)


def _instrumented(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        log = _fallback_call_log.get()
        if log is not None:
            log.append(func.__name__)
        return func(*args, **kwargs)
    return wrapper


@_instrumented
def legacy_default_driver_context() -> "DriverContext":
    """Resolve the plugin to use when a public caller supplies no context.

    Why: public CLI and Python callers have always been able to omit the
    plugin/context entirely, and something has to answer. This used to import
    ``CardiacFoamPlugin`` directly, which put a hard cardiac dependency in the
    one package whose whole purpose is to know no cardiology -- touching the
    public edge of a core-only install raised ``ModuleNotFoundError: No module
    named 'omnidriver.cardiacfoam'``.

    It now resolves through the same ``omnidriver.plugins`` entry-point group
    that ``--plugin`` reads, so core names no solver at all. The selection rule
    lives in :func:`plugin_discovery._default_selection`; in short, exactly one
    installed adapter wins, no adapter is an error, and several adapters
    require explicit selection. Core does not manufacture a solver context
    when no adapter is installed.

    The context is built fresh on each call, as it always has been -- core must
    not retain one in module state.

    Activation: the public boundary receives no explicit plugin context.
    Preserved by: core plugin-context, CLI matrix, validation, and strict-plan
    tests.
    """

    from .plugin_discovery import default_discovered_context

    return default_discovered_context()


def resolve_public_driver_context(
    driver_context: "DriverContext | None",
) -> "DriverContext":
    """Resolve the unchanged optional-context public API convention once."""

    return driver_context if driver_context is not None else legacy_default_driver_context()


@_instrumented
def legacy_case_marker(plugin, case_root) -> bool:
    """Plugins predating has_case_marker(). A plugin that does not implement
    the hook gets ``False`` and must declare its own filesystem marker."""

    del plugin, case_root
    return False


@_instrumented
def legacy_case_runnable_without_workflow(plugin, case_root) -> bool:
    """Plugins predating is_case_runnable_without_workflow(). A plugin that
    does not implement the hook gets ``False``. Adapter-declared entrypoints
    are checked separately by the registry."""

    del plugin, case_root
    return False


@_instrumented
def legacy_run_document_config(plugin, spec):
    """Plugins predating build_run_document_config(). A plugin that does not
    implement the hook gets an empty config and no diagnostics -- it
    constrains nothing, exactly as :func:`legacy_run_document_config_schema`
    hands it a fully open schema."""

    del plugin, spec
    return {}, ()


@_instrumented
def legacy_run_document_config_schema(plugin) -> dict:
    """v1 plugins predate get_run_document_config_schema(). A plugin that does
    not implement the hook gets a fully open schema (no constraint) and must
    declare its own by migrating to v2."""

    del plugin
    return {"type": "object", "additionalProperties": True}


@_instrumented
def legacy_nondimensional_case(plugin, spec) -> bool:
    """Plugins predating is_nondimensional_case(). A plugin that does not
    implement the hook gets ``False``: its meshes are dimensional until it
    says otherwise, which is the conservative answer -- it keeps mesh-scale
    diagnostics ON rather than silently exempting a case from them."""

    del plugin, spec
    return False


@_instrumented
def legacy_base_mesh_geometry_diagnostics(case_root) -> tuple:
    """Plugins predating get_base_mesh_geometry_diagnostics().

    A plugin that predates the mesh-diagnostics hook contributes no base
    geometry evidence. Format-specific mesh interpretation belongs to the
    selected adapter."""

    del case_root
    return ()


@_instrumented
def legacy_environment_diagnostics(
    workflow_dag, *, env=None, environment_source=None, driver_context=None,
) -> tuple:
    """Plugins predating get_environment_diagnostics().

    A plugin that predates the environment-diagnostics hook contributes an
    explicit unsupported-capability diagnostic. Core does not infer a runtime
    or source a shell profile on its behalf."""

    del workflow_dag, env, environment_source, driver_context
    from .planning_types import diagnostic

    return (diagnostic(
        "error",
        "environment_capability_unavailable",
        "The selected adapter does not declare environment validation.",
        source="adapter",
    ),)


@_instrumented
def legacy_configured_environment(env, driver_context) -> dict:
    """Plugins predating get_configured_environment(). sweep_runner.py has
    no adapter-specific environment contract to apply, so the mapping is
    preserved unchanged."""

    del driver_context
    return dict(env)


@_instrumented
def legacy_load_environment(*, environment_source, driver_context) -> dict:
    """Plugins predating get_loaded_environment() use the current process
    environment unchanged. This keeps legacy callers usable in a core-only
    installation without assuming a shell-profile format."""

    del environment_source, driver_context
    import os

    return dict(os.environ)


@_instrumented
def legacy_apply_overrides(
    overrides, *, case_root, driver_context, execution_env=None,
) -> tuple[dict, ...]:
    """Plugins predating apply_overrides() cannot apply format-specific
    overrides.

    Validation and application are one call because core has only ever used
    them together, and splitting them would let a caller apply without
    validating. Raises OverrideError, a ValueError subclass, so core catches
    ValueError and needs no import of the exception type.

    There is no neutral default here the way there is for e.g. environment
    diagnostics: applying an override means writing bytes into a dict file
    whose syntax only the selected adapter's mutators understand, so a
    plugin with no own ``apply_overrides()`` hook genuinely cannot be swept
    into this path (future/ENVIRONMENT_CONTRACT.md §10, Tier 3) -- same shape as ``route_sweep_case_values``/
    ``materialize_sweep_case`` refusing by name rather than pretending to be
    neutral. Without this catch, the import raised ModuleNotFoundError
    uncaught -- cli.py's ``except (OSError, ValueError)`` around this call
    does not catch it, so it reached the terminal as a raw traceback."""

    del overrides, case_root, driver_context, execution_env
    raise ValueError(
        "the selected adapter does not implement apply_overrides(); "
        "strict applying is not supported for this plugin"
    )


@_instrumented
def legacy_override_target_paths(overrides, *, case_root, driver_context) -> tuple:
    """An adapter without a mutator cannot declare mutation targets."""

    del overrides, case_root, driver_context
    raise ValueError(
        "the selected adapter does not implement override target declaration"
    )


@_instrumented
def legacy_inspect_effective_configuration(
    *, case_root, driver_context, execution_env=None,
) -> tuple[dict, ...]:
    """A plugin without an inspection hook contributes no fabricated evidence."""
    del case_root, driver_context, execution_env
    return ()


@_instrumented
def legacy_function_object_field_diagnostics(case_root, *, samplable) -> tuple:
    """Plugins predating the function-object hook emit no format-specific
    diagnostics."""

    del case_root, samplable
    return ()


@_instrumented
def legacy_case_dict_key_diagnostics(case_root, *, catalogued_paths, dict_relpaths) -> tuple:
    """Plugins predating the dictionary-key hook emit no format-specific
    diagnostics."""

    del case_root, catalogued_paths, dict_relpaths
    return ()


@_instrumented
def legacy_dict_key_scanner():
    """Plugins predating a C++ dictionary-key scanner hook emit an empty
    report. Format-specific source scanning belongs to the adapter.

    Returns only the C++ REPORT. The catalogue-path vocabulary that used to
    come back alongside it is core's own (see
    core/contracts/catalogue_paths.py) and must not be routed through here:
    format-specific parsing must remain in the adapter even when the adapter
    implements get_case_dict_key_diagnostics and never reaches this fallback.

    **Corrected 2026-09-22:** this used to say "strict planning calls it
    eagerly to build an argument" -- true when ``strict_planning.py`` imported
    and invoked this function directly at module scope, which was the defect
    Task 11 fixed. It is now reached only as ``DictKeyScannerCapability``'s
    declared fallback (``plugin_capabilities._DictKeyScannerAdapter.scan``),
    when a plugin implements no ``get_dict_key_scanner`` hook of its own."""

    class _EmptyReport:
        def to_json(self):
            return {
                "unmatched_cxx_reads": [],
                "stale_paths": [],
                "unmatched_subdicts": [],
                "unused_allowlist": [],
            }

    def _report(*args, **kwargs):
        del args, kwargs
        return _EmptyReport()

    return _report


@_instrumented
def legacy_route_sweep_case(plugin, *, base, resolved_axis_values, driver_context):
    """Plugins predating route_sweep_case_values().

    Unlike every other fallback here, a neutral empty return is not available:
    routing produces the values a case is then materialized from, so an empty
    routing silently yields a case that is not the one the sweep asked for.
    The honest neutral is to refuse, naming the hook the plugin must
    implement.

    Historical note: an earlier implementation routed against one solver's
    dictionary vocabulary. That behavior is no longer active; routing now
    refuses unless the selected adapter declares the operation."""

    del base, resolved_axis_values, driver_context
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    raise SweepValidationError(
        f"plugin {getattr(plugin, 'plugin_id', '<unknown>')!r} does not implement "
        "route_sweep_case_values(); omnidriver cannot route sweep axes for it. "
        "Implement route_sweep_case_values(base, resolved_axis_values, "
        "driver_context) on the plugin to support sweeps."
    )


@_instrumented
def legacy_materialize_sweep_case(plugin, *, case_dir, routed) -> None:
    """Plugins predating materialize_sweep_case(). Refuses for the same
    reason as :func:`legacy_route_sweep_case`.

    This refusal is intentional. A missing materializer cannot be replaced by
    another adapter's writer. The historical defect that motivated this seam
    involved one solver's generated script, but that behavior is no longer
    active."""

    del case_dir, routed
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    raise SweepValidationError(
        f"plugin {getattr(plugin, 'plugin_id', '<unknown>')!r} does not implement "
        "materialize_sweep_case(); omnidriver cannot materialize sweep cases "
        "for it. Implement materialize_sweep_case(case_dir, routed) on the "
        "plugin to support sweeps."
    )


@_instrumented
def legacy_solver_commands(plugin) -> frozenset[str]:
    """v1 plugins predate get_solver_commands(). A plugin that does not
    implement the hook gets none authorized and must declare its commands by
    migrating to v2."""

    del plugin
    return frozenset()


@_instrumented
def legacy_auxiliary_commands(plugin) -> frozenset[str]:
    """v1 plugins predate get_auxiliary_commands(). Same rule as
    :func:`legacy_solver_commands`: a plugin that does not implement the hook
    gets no non-solver commands authorized."""

    del plugin
    return frozenset()


@_instrumented
def legacy_environment_commands(plugin) -> frozenset[str]:
    """Plugins without an environment declaration authorize no such commands."""

    del plugin
    return frozenset()


@_instrumented
def legacy_is_installed_environment_command(plugin, command: str) -> bool:
    """A missing environment declaration cannot authorize dynamic commands."""

    del plugin, command
    return False


@_instrumented
def legacy_utility_manifests(plugin) -> dict:
    """v1 plugins predate get_utility_manifests(). A plugin that does not
    implement the hook gets no utility catalog."""

    del plugin
    return {}


@_instrumented
def legacy_utility_roots(plugin) -> tuple:
    """v1 plugins predate get_utility_roots(). A plugin that does not
    implement the hook gets no utility roots."""

    del plugin
    return ()


@_instrumented
def legacy_resolve_case_models(plugin, case_root) -> dict:
    """v1 plugins predate resolve_case_models(). A plugin that does not
    implement the hook gets nothing and must declare its own resolution by
    migrating to v2."""

    del plugin, case_root
    return {}


@_instrumented
def legacy_samplable_fields(plugin, resolved) -> dict:
    """v1 plugins predate get_samplable_fields(). Same rule as
    :func:`legacy_resolve_case_models`: a plugin that does not implement the
    hook names no fields."""

    del plugin, resolved
    return {}


@_instrumented
def legacy_override_schema(plugin, tutorial_name: str, make_spec_info: dict) -> dict:
    """v1 plugins predate get_override_schema(). A plugin that does not
    implement the hook gets an empty schema and must declare its own by
    migrating to v2."""

    del plugin, tutorial_name, make_spec_info
    return {}


@_instrumented
def legacy_dict_entry_catalog(plugin) -> dict:
    """v1 plugins predate get_dict_entry_catalog(). Same rule as
    :func:`legacy_override_schema`: a plugin that does not implement the hook
    gets no dictionary catalog."""

    del plugin
    return {}


@_instrumented
def legacy_phases(plugin) -> tuple[str, ...]:
    """The dictionary phases for a plugin that does not implement
    ``get_phases()``: those its own ``DictEntry`` values declare, sorted for
    determinism.

    Sorted, not ordered -- and the order is the semantics, since
    ``primary_phase()`` returns the first phase in it that an entry claims. A
    plugin with multi-phase entries should implement ``get_phases()`` rather
    than accept an alphabetical guess. What this must never do is hand back
    phases from another adapter to a plugin that never declared them: that
    was the silent defect this replaces.

    Ungated -- no ``plugin_id`` check. It derives from the plugin's own
    ``DictEntry`` values, so it is correct for every plugin."""

    declared: set[str] = set()
    hook = getattr(plugin, "get_dict_entries", None)
    for entry in (hook() if callable(hook) else ()):
        declared.update(entry.phases)
    return tuple(sorted(declared))


@_instrumented
def legacy_describe_config_resolution(plugin) -> str:
    """v1 plugins predate describe_config_resolution(). A plugin that does not
    implement the hook gets a plugin-neutral sentence."""

    del plugin
    return "The plugin's configuration files resolve into a valid RunDocument config."


@_instrumented
def legacy_case_runtime_conventions():
    """Neutral fallback for plugins that declare no generated case paths.

    A foreign environment must not lose an authored ``data`` or
    ``postProcessing`` directory merely because an OpenFOAM sweep once used
    those names for generated output.
    """

    from .plugin_capabilities import CaseRuntimeConventions

    return CaseRuntimeConventions()


@_instrumented
def legacy_report_catalog(plugin) -> tuple:
    """v1 plugins predate get_report_catalog(). Same rule as
    :func:`legacy_override_schema`: a plugin that does not implement the hook
    gets no reports and must declare its own by migrating to v2."""

    del plugin
    return ()


@_instrumented
def legacy_named_catalogs(plugin) -> dict:
    """v1 plugins predate get_named_catalogs(). Same rule as
    :func:`legacy_override_schema`: a plugin that does not implement the hook
    gets no named catalogs and must declare its own by migrating to v2."""

    del plugin
    return {}


@_instrumented
def legacy_override_scopes(plugin) -> tuple:
    """v1/v2 plugins predate get_override_scopes(). A plugin that does not
    implement the hook gets no override scopes and must declare its own by
    implementing get_override_scopes()."""

    del plugin
    return ()


@_instrumented
def legacy_dict_regeneration_scopes(plugin) -> tuple:
    """v1/v2 plugins predate get_regeneration_scopes(). A plugin that does not
    implement the hook gets no regeneration scopes and must declare its own
    by implementing get_regeneration_scopes()."""

    del plugin
    return ()


#: legacy_tutorial_records, legacy_axis_catalog, legacy_record_key_validation,
#: and legacy_case_value_comparator (2026-09-24, tutorial-record design) were
#: deleted here (review finding M1). All four capabilities they backed
#: (TutorialRecordCapability, AxisCapability, RecordKeyValidationCapability,
#: CaseValueComparisonCapability) are now declared ``:fallback: none``, like
#: ConfigValueCapability/CaseWriterCapability: their adapters
#: (`plugin_capabilities.py`) return ``None`` directly when a plugin declares
#: no hook, with no compatibility function standing in for one. A silent
#: neutral fallback here was the wrong shape for what these four seams guard
#: -- a missing record-key validator or case-value comparator must stop a
#: record case from running at all (`record_execution._resolve_and_split`
#: refuses by name), not quietly agree to run it unchecked.
