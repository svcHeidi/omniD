"""Named fallback answers for optional plugin members.

Each ``absent_*`` function is the answer core gives when the active plugin
stack does not implement one particular optional hook, kept named and
documented rather than rediscovered ad hoc inside solver-neutral code.
"""

from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager

_fallback_call_log: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_fallback_call_log", default=None,
)


@contextmanager
def track_fallback_calls():
    """Yield a list that fills with the name of every ``absent_*`` fallback
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
def absent_environment_diagnostics(
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
def absent_configured_environment(env, driver_context) -> dict:
    """Plugins predating get_configured_environment(). sweep_runner.py has
    no adapter-specific environment contract to apply, so the mapping is
    preserved unchanged."""

    del driver_context
    return dict(env)


@_instrumented
def absent_load_environment(*, environment_source, driver_context) -> dict:
    """A plugin without get_loaded_environment() uses the current process
    environment unchanged. This keeps such callers usable in a core-only
    installation without assuming a shell-profile format."""

    del environment_source, driver_context
    import os

    return dict(os.environ)


@_instrumented
def absent_apply_overrides(
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
    into this path (future/ENVIRONMENT_CONTRACT.md §10, Tier 3): it refuses by
    name rather than pretending to be neutral."""

    del overrides, case_root, driver_context, execution_env
    raise ValueError(
        "the selected adapter does not implement apply_overrides(); "
        "strict applying is not supported for this plugin"
    )


@_instrumented
def absent_override_target_paths(overrides, *, case_root, driver_context) -> tuple:
    """An adapter without a mutator cannot declare mutation targets."""

    del overrides, case_root, driver_context
    raise ValueError(
        "the selected adapter does not implement override target declaration"
    )


@_instrumented
def absent_inspect_effective_configuration(
    *, case_root, driver_context, execution_env=None,
) -> tuple[dict, ...]:
    """A plugin without an inspection hook contributes no fabricated evidence."""
    del case_root, driver_context, execution_env
    return ()


@_instrumented
def absent_dict_key_scanner():
    """Plugins with no C++ dictionary-key scanner report nothing. Reached
    only as ``DictKeyScannerCapability``'s declared fallback."""

    class _EmptyReport:
        def to_json(self):
            return {"contradictions": [], "uncatalogued": [], "unresolved": [], "selector_values": {}}

    def _report(*args, **kwargs):
        del args, kwargs
        return _EmptyReport()

    return _report


@_instrumented
def absent_solver_commands(plugin) -> frozenset[str]:
    """get_solver_commands() is optional. A plugin that does not
    implement it gets none authorized and must declare its commands by
    implementing get_solver_commands()."""

    del plugin
    return frozenset()


@_instrumented
def absent_auxiliary_commands(plugin) -> frozenset[str]:
    """get_auxiliary_commands() is optional. Same rule as
    :func:`absent_solver_commands`: a plugin that does not implement it
    gets no non-solver commands authorized."""

    del plugin
    return frozenset()


@_instrumented
def absent_environment_commands(plugin) -> frozenset[str]:
    """Plugins without an environment declaration authorize no such commands."""

    del plugin
    return frozenset()


@_instrumented
def absent_is_installed_environment_command(plugin, command: str) -> bool:
    """A missing environment declaration cannot authorize dynamic commands."""

    del plugin, command
    return False


@_instrumented
def absent_utility_manifests(plugin) -> dict:
    """get_utility_manifests() is optional. A plugin that does not
    implement it gets no utility catalog."""

    del plugin
    return {}


@_instrumented
def absent_utility_roots(plugin) -> tuple:
    """get_utility_roots() is optional. A plugin that does not
    implement it gets no utility roots."""

    del plugin
    return ()


@_instrumented
def absent_resolve_case_models(plugin, case_root) -> dict:
    """resolve_case_models() is optional. A plugin that does not
    implement it gets nothing and must declare its own resolution by
    implementing resolve_case_models()."""

    del plugin, case_root
    return {}


@_instrumented
def absent_samplable_fields(plugin, resolved) -> dict:
    """get_samplable_fields() is optional. Same rule as
    :func:`absent_resolve_case_models`: a plugin that does not implement the
    hook names no fields."""

    del plugin, resolved
    return {}


@_instrumented
def absent_dict_entry_catalog(plugin) -> dict:
    """get_dict_entry_catalog() is optional. Same rule as
    :func:`absent_resolve_case_models`: a plugin that does not implement it
    gets no dictionary catalog."""

    del plugin
    return {}


@_instrumented
def absent_phases(plugin) -> tuple[str, ...]:
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
def absent_case_runtime_conventions():
    """Neutral fallback for plugins that declare no generated case paths.

    A foreign environment must not lose an authored ``data`` or
    ``postProcessing`` directory merely because an OpenFOAM sweep once used
    those names for generated output.
    """

    from .plugin_capabilities import CaseRuntimeConventions

    return CaseRuntimeConventions()


@_instrumented
def absent_report_catalog(plugin) -> tuple:
    """get_report_catalog() is optional. Same rule as
    :func:`absent_resolve_case_models`: a plugin that does not implement it
    gets no reports and must declare its own by implementing
    get_report_catalog()."""

    del plugin
    return ()


@_instrumented
def absent_named_catalogs(plugin) -> dict:
    """get_named_catalogs() is optional. Same rule as
    :func:`absent_resolve_case_models`: a plugin that does not implement it
    gets no named catalogs and must declare its own by implementing
    get_named_catalogs()."""

    del plugin
    return {}


@_instrumented
def absent_override_scopes(plugin) -> tuple:
    """get_override_scopes() is optional. A plugin that does not
    implement it gets no override scopes and must declare its own by
    implementing get_override_scopes()."""

    del plugin
    return ()


@_instrumented
def absent_dict_regeneration_scopes(plugin) -> tuple:
    """get_regeneration_scopes() is optional. A plugin that does not
    implement it gets no regeneration scopes and must declare its own
    by implementing get_regeneration_scopes()."""

    del plugin
    return ()


#: TutorialRecordCapability, RecordKeyValidationCapability and
#: CaseValueComparisonCapability declare ``:fallback: none``, like
#: ConfigValueCapability/CaseWriterCapability, and have no ``absent_*``
#: function here: their adapters (`plugin_capabilities.py`) return ``None``
#: directly when a plugin declares no hook. A silent neutral fallback is the
#: wrong shape for what these seams guard -- a missing record-key validator
#: or case-value comparator must stop a record case from running at all
#: (`record_execution._resolve_and_split` refuses by name), not quietly agree
#: to run it unchecked. A record carries its own axes (``TutorialRecord.axes``).
