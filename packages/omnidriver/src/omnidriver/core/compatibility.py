"""Named defaults for optional plugin capabilities.

Required plugin API members are validated before a :class:`DriverContext`
exists, so functions in this module do not make missing required members work.
They define one of three live behaviors: the supported public no-context
convention, a neutral default for an optional hook, or an explicit refusal
when no neutral behavior exists. Keeping those decisions named makes absence
semantics observable.
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
    invoked inside the ``with`` block, in call order."""
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

    Resolution uses the ``omnidriver.plugins`` entry-point group. Exactly one
    installed adapter is selected; zero or multiple adapters require an
    explicit choice. A fresh context is returned on every call.
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
    """Without the optional ``has_case_marker()`` hook, return ``False``.

    A plugin must declare its own filesystem marker to return ``True``.
    """

    del plugin, case_root
    return False


@_instrumented
def legacy_case_runnable_without_workflow(plugin, case_root) -> bool:
    """Without this optional hook, return ``False``.

    Adapter-declared entrypoints are checked separately by the registry.
    """

    del plugin, case_root
    return False


@_instrumented
def legacy_run_document_config(plugin, spec):
    """Without the optional build hook, return no generated config.

    Their required ``get_run_document_config_schema()`` still decides whether
    that empty object is valid; Core does not invent a second schema route.
    """

    del plugin, spec
    return {}, ()


@_instrumented
def legacy_nondimensional_case(plugin, spec) -> bool:
    """Without this optional hook, treat the mesh as dimensional.

    This conservative answer keeps mesh-scale diagnostics on rather than
    silently exempting a case from them.
    """

    del plugin, spec
    return False


@_instrumented
def legacy_base_mesh_geometry_diagnostics(case_root) -> tuple:
    """Without this optional hook, contribute no base geometry evidence.

    Format-specific mesh interpretation belongs to the selected adapter.
    """

    del case_root
    return ()


@_instrumented
def legacy_environment_diagnostics(
    workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None,
) -> tuple:
    """Without this optional hook, report an unsupported capability.

    Core does not infer a runtime or source a shell profile on the plugin's
    behalf.
    """

    del workflow_dag, env, explicit_bashrc, driver_context
    from .planning_types import diagnostic

    return (diagnostic(
        "error",
        "environment_capability_unavailable",
        "The selected adapter does not declare environment validation.",
        source="adapter",
    ),)


@_instrumented
def legacy_configured_environment(env, driver_context) -> dict:
    """Without this optional hook, preserve the environment unchanged.

    ``sweep_runner.py`` has no adapter-specific environment contract to apply.
    """

    del driver_context
    return dict(env)


@_instrumented
def legacy_load_environment(*, explicit_bashrc, driver_context) -> dict:
    """Without this optional hook, use the current process environment.

    This supports a core-only installation without assuming a shell-profile
    format.
    """

    del explicit_bashrc, driver_context
    import os

    return dict(os.environ)


@_instrumented
def legacy_apply_overrides(
    overrides, *, case_root, driver_context, execution_env=None,
) -> tuple[dict, ...]:
    """Refuse format-specific overrides when the adapter has no mutator.

    The selected adapter owns validation and serialization of its format, so
    Core has no neutral implementation.
    """

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
    """Without this optional hook, emit no format-specific diagnostics."""

    del case_root, samplable
    return ()


@_instrumented
def legacy_case_dict_key_diagnostics(case_root, *, catalogued_paths, dict_relpaths) -> tuple:
    """Without this optional hook, emit no format-specific diagnostics."""

    del case_root, catalogued_paths, dict_relpaths
    return ()


@_instrumented
def legacy_route_sweep_case(plugin, *, base, resolved_axis_values, driver_context):
    """Without this optional hook, refuse sweep routing.

    Routing produces the values that materialization consumes, so an empty
    result would describe the wrong case.
    """

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
    """Without this optional hook, refuse sweep materialization.

    A missing materializer cannot be replaced by another adapter's writer.
    """

    del case_dir, routed
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    raise SweepValidationError(
        f"plugin {getattr(plugin, 'plugin_id', '<unknown>')!r} does not implement "
        "materialize_sweep_case(); omnidriver cannot materialize sweep cases "
        "for it. Implement materialize_sweep_case(case_dir, routed) on the "
        "plugin to support sweeps."
    )


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
def legacy_phases(plugin) -> tuple[str, ...]:
    """Return declared dictionary phases in deterministic fallback order.

    Plugins with multi-phase entries should implement ``get_phases()`` because
    phase order determines the primary editing phase.
    """

    declared: set[str] = set()
    for entry in plugin.get_dict_entries():
        declared.update(entry.phases)
    return tuple(sorted(declared))


@_instrumented
def legacy_describe_config_resolution(plugin) -> str:
    """Without the optional description hook, return neutral prose."""

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
    """Without the optional catalog hook, declare no reports."""

    del plugin
    return ()


@_instrumented
def legacy_named_catalogs(plugin) -> dict:
    """Without the optional hook, declare no named catalogs."""

    del plugin
    return {}


@_instrumented
def legacy_override_scopes(plugin) -> tuple:
    """Without this optional hook, declare no override scopes."""

    del plugin
    return ()


@_instrumented
def legacy_dict_regeneration_scopes(plugin) -> tuple:
    """Without this optional hook, declare no regeneration scopes."""

    del plugin
    return ()
