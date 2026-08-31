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
    """Return the historical built-in cardiacFoam context.

    Why: public CLI and Python callers have always selected cardiacFoam when no
    plugin/context is supplied.
    Activation: the public boundary receives no explicit plugin context.
    Preserved by: core plugin-context, CLI matrix, validation, and strict-plan
    tests.
    Plan 2 seam: default selection or deprecation policy may change there.
    """

    from .plugin_interface import driver_context
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    target = "omnidriver.cardiacfoam.cardiacfoam_plugin:CardiacFoamPlugin"
    return driver_context(
        CardiacFoamPlugin(), source=f"trusted-import:{target}",
    )


def resolve_public_driver_context(
    driver_context: "DriverContext | None",
) -> "DriverContext":
    """Resolve the unchanged optional-context public API convention once."""

    return driver_context if driver_context is not None else legacy_default_driver_context()


@_instrumented
def legacy_generic_case_mutation(*args, **kwargs) -> None:
    """Preserve direct callers of the formerly cardiac-owned generic factory.

    Why: the historical public ``make_spec`` mutated the cardiac electro and
    physics dictionaries.  Activation: a caller imports core ``make_spec``
    directly rather than the solver-neutral registry alias.  Tests in the
    cardiac generic-case and template suites preserve it.  Plan 2 may replace
    this with explicit generic dictionary mutations.
    """

    from omnidriver.cardiacfoam.generic_case_mutation import apply_case_mutation

    apply_case_mutation(*args, **kwargs)


# The dictionary files the historical generic-case factory addressed, keyed by
# the generic ``dict_file_relpaths`` names.  Insertion order matters: the first
# entry is the "primary" file whose presence marks a folder as non-generic, and
# ``electroProperties`` has always been that marker.
_LEGACY_GENERIC_CASE_DICT_FILES = (
    ("electro", "constant/electroProperties"),
    ("physics", "constant/physicsProperties"),
)

# Historical cardiac-named ``make_spec`` keyword arguments, mapped onto the
# generic ``(bucket, dict-file name)`` they now address.
_LEGACY_GENERIC_CASE_ALIASES = {
    "electro_properties_relpath": ("relpaths", "electro"),
    "physics_properties_relpath": ("relpaths", "physics"),
    "electro_property_overrides": ("overrides", "electro"),
    "physics_property_overrides": ("overrides", "physics"),
}


@_instrumented
def legacy_generic_case_dict_file_relpaths() -> dict[str, str]:
    """Return the dictionary files core ``make_spec`` has always defaulted to.

    Why: the historical signature defaulted ``electro_properties_relpath`` and
    ``physics_properties_relpath`` to fixed cardiac paths, and the generic-case
    detection keyed off the first of them.  Activation: a caller of core
    ``make_spec`` declares no ``dict_file_relpaths``.  Preserved by the core
    generic-case and strict-plan suites.  Plan 2 seam: a plugin declaring its
    own dictionary files makes this default unnecessary.
    """

    return dict(_LEGACY_GENERIC_CASE_DICT_FILES)


def legacy_generic_case_alias_names() -> frozenset[str]:
    """Names :func:`legacy_generic_case_dict_file_aliases` recognises.

    Uninstrumented on purpose: callers use it to *decide* whether a legacy
    alias is present at all, so consulting it is not itself a fallback.
    """

    return frozenset(_LEGACY_GENERIC_CASE_ALIASES)


@_instrumented
def legacy_generic_case_dict_file_aliases(
    payload,
) -> tuple[dict, dict, list[str]]:
    """Translate deprecated cardiac-named generic-case keywords.

    Why: ``electro_property_overrides`` and friends are advertised as common
    override keys and reach ``make_spec`` verbatim from ``--config``/``--set``.
    Activation: any such key appears in a ``make_spec`` call or in a ``cases``
    entry.  Returns ``(relpaths, overrides, unknown_keys)`` so the caller keeps
    ownership of rejecting genuinely unknown keywords.  Plan 2 seam: the
    aliases may be dropped once callers migrate to ``dict_file_relpaths`` and
    ``dict_file_overrides``.
    """

    relpaths: dict = {}
    overrides: dict = {}
    unknown: list[str] = []
    for key, value in dict(payload).items():
        target = _LEGACY_GENERIC_CASE_ALIASES.get(key)
        if target is None:
            unknown.append(key)
            continue
        bucket, name = target
        (relpaths if bucket == "relpaths" else overrides)[name] = value
    return relpaths, overrides, unknown


@_instrumented
def legacy_case_marker(plugin, case_root) -> bool:
    """Plugins predating has_case_marker(). A plugin that does not implement
    the hook gets ``False`` and must declare its own filesystem marker."""

    del plugin, case_root
    return False


@_instrumented
def legacy_case_runnable_without_workflow(plugin, case_root) -> bool:
    """Plugins predating is_case_runnable_without_workflow(). A plugin that
    does not implement the hook gets ``False`` -- core then falls back to an
    executable ``Allrun``, which is plugin-neutral filesystem evidence."""

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

    Why: strict_planning.py has always run the OpenFOAM polyMesh scale
    classifier unconditionally, for every plugin, without checking which one
    was active -- the classifier isn't actually solver-neutral (it parses
    OpenFOAM's polyMesh format), that was just never visible while core and
    the OpenFOAM environment were one package. Preserved as-is here rather
    than narrowed to cardiac-only, since narrowing it would change observable
    behavior for any other plugin (there wasn't one before this migration).
    Plan 2 seam: a genuinely non-OpenFOAM plugin should implement
    get_base_mesh_geometry_diagnostics itself (returning ``()`` is valid) or
    override this default."""

    from omnidriver.openfoam.mesh_geometry import mesh_geometry_diagnostics

    return mesh_geometry_diagnostics(case_root)


@_instrumented
def legacy_environment_diagnostics(
    workflow_dag, *, env=None, openfoam_bashrc=None, driver_context=None,
) -> tuple:
    """Plugins predating get_environment_diagnostics().

    Why: strict_planning.py has always preflighted every plan against the
    OpenFOAM runtime environment (WM_PROJECT_DIR, bashrc sourcing, PATH)
    unconditionally, the same "was never actually solver-neutral" situation
    as legacy_base_mesh_geometry_diagnostics. Preserved as-is; a non-OpenFOAM
    plugin implements get_environment_diagnostics itself."""

    from omnidriver.openfoam.environment_preflight import _environment_diagnostics

    return _environment_diagnostics(
        workflow_dag, env=env, openfoam_bashrc=openfoam_bashrc,
        driver_context=driver_context,
    )


@_instrumented
def legacy_configured_environment(env, driver_context) -> dict:
    """Plugins predating get_configured_environment(). sweep_runner.py has
    always applied the OpenFOAM plugin environment contract unconditionally,
    same historical-behavior-preserved reasoning as the other environment
    fallbacks above."""

    from omnidriver.openfoam.openfoam_environment import configure_plugin_environment

    return configure_plugin_environment(env, driver_context).env


@_instrumented
def legacy_load_environment(*, explicit_bashrc, driver_context) -> dict:
    """Plugins predating get_loaded_environment(). cli.py has always sourced an
    OpenFOAM bashrc before executing a workflow, unconditionally and for every
    plugin -- same historical-behavior-preserved reasoning as the other
    environment fallbacks above.

    This exists so cli.py does not import omnidriver.openfoam at module scope.
    It did, on two lines, which made ``import omnidriver.cli`` raise
    ModuleNotFoundError in a core-only install and took the entire CLI surface
    with it."""

    from omnidriver.openfoam.openfoam_environment import load_openfoam_environment

    return dict(
        load_openfoam_environment(
            explicit_bashrc=explicit_bashrc, driver_context=driver_context,
        ).env
    )


@_instrumented
def legacy_apply_overrides(overrides, *, case_root, driver_context) -> None:
    """Plugins predating apply_overrides(). The ``step --strict --apply`` path
    has always validated and applied overrides through the OpenFOAM dictionary
    mutators, for every plugin.

    Validation and application are one call because core has only ever used
    them together, and splitting them would let a caller apply without
    validating. Raises OverrideError, a ValueError subclass, so core catches
    ValueError and needs no import of the exception type."""

    from omnidriver.openfoam.apply_overrides import apply_overrides, validate_overrides

    validate_overrides(overrides, driver_context=driver_context)
    apply_overrides(overrides, case_root=case_root, driver_context=driver_context)


@_instrumented
def legacy_function_object_field_diagnostics(case_root, *, samplable) -> tuple:
    """Plugins predating get_function_object_field_diagnostics().
    strict_planning.py has always warned about controlDict function objects
    sampling fields absent from the capability manifest, by parsing the
    OpenFOAM controlDict directly via foamlib -- same
    was-never-actually-solver-neutral situation as the other diagnostics
    fallbacks in this file."""

    from omnidriver.openfoam.function_object_fields import function_object_field_diagnostics

    return function_object_field_diagnostics(case_root, samplable=samplable)


@_instrumented
def legacy_case_dict_key_diagnostics(case_root, *, catalogued_paths, dict_relpaths) -> tuple:
    """Plugins predating get_case_dict_key_diagnostics(). Same reasoning as
    legacy_function_object_field_diagnostics: preserved as-is, parses
    OpenFOAM dict files via foamlib."""

    from omnidriver.openfoam.case_dict_keys import case_dict_key_diagnostics

    return case_dict_key_diagnostics(
        case_root, catalogued_paths=catalogued_paths, dict_relpaths=dict_relpaths,
    )


@_instrumented
def legacy_dict_key_scanner():
    """Plugins predating a C++ dict-key scanner hook. strict_planning has
    always scanned OpenFOAM C++ sources for dictionary-read call sites, for
    every plugin -- the same was-never-actually-solver-neutral situation as
    legacy_case_dict_key_diagnostics, which parses the dicts themselves.
    Preserved as-is; a non-OpenFOAM plugin implements this itself.

    Returns only the C++ REPORT. The catalogue-path vocabulary that used to
    come back alongside it is core's own (see
    core/contracts/catalogue_paths.py) and must not be routed through here:
    strict_plan calls it eagerly to build an argument, so an openfoam import
    at that point fires even for a plugin that implements
    get_case_dict_key_diagnostics and would never reach the fallback."""

    from omnidriver.openfoam.dict_keys_scanner import strict_dict_key_report

    return strict_dict_key_report


@_instrumented
def legacy_route_sweep_case(plugin, *, base, resolved_axis_values, driver_context):
    """Plugins predating route_sweep_case_values().

    Unlike every other fallback here, a neutral empty return is not available:
    routing produces the values a case is then materialized from, so an empty
    routing silently yields a case that is not the one the sweep asked for.
    The honest neutral is to refuse, naming the hook the plugin must
    implement.

    The cardiac router validates axes against ``electroProperties``/
    ``physicsProperties`` vocabulary, so ungated it rejected a non-cardiac
    plugin's axes in cardiac terms -- or, worse, accepted them."""

    del base, resolved_axis_values, driver_context
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    raise SweepValidationError(
        f"plugin {getattr(plugin, 'plugin_id', '<unknown>')!r} does not implement "
        "route_sweep_case_values(); driverFOAM cannot route sweep axes for it. "
        "Implement route_sweep_case_values(base, resolved_axis_values, "
        "driver_context) on the plugin to support sweeps."
    )


@_instrumented
def legacy_materialize_sweep_case(plugin, *, case_dir, routed) -> None:
    """Plugins predating materialize_sweep_case(). Refuses for the same
    reason as :func:`legacy_route_sweep_case`.

    This is the fallback with real teeth. The cardiac materializer writes an
    ``Allrun`` containing a hardcoded ``cardiacFoam`` command, so ungated it
    generated a case invoking the cardiacFoam binary under whichever plugin
    was loaded (reproduced against GenericOpenFOAMPlugin, 2026-08-19)."""

    del case_dir, routed
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    raise SweepValidationError(
        f"plugin {getattr(plugin, 'plugin_id', '<unknown>')!r} does not implement "
        "materialize_sweep_case(); driverFOAM cannot materialize sweep cases "
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
    cardiacFoam's four to a plugin that never declared them: that was the
    silent defect this replaces.

    Ungated -- no ``plugin_id`` check. It derives from the plugin's own
    ``DictEntry`` values, so it is correct for every plugin."""

    declared: set[str] = set()
    for entry in plugin.get_dict_entries():
        declared.update(entry.phases)
    return tuple(sorted(declared))


@_instrumented
def legacy_describe_config_resolution(plugin) -> str:
    """v1 plugins predate describe_config_resolution(). A plugin that does not
    implement the hook gets a plugin-neutral sentence."""

    del plugin
    return "The plugin's configuration files resolve into a valid RunDocument config."


@_instrumented
def legacy_config_value_reader(path, key: str) -> str | None:
    """Preserve the historical direct-foamlib read for plugins that don't
    implement get_config_value_reader.

    Why: every existing plugin call site read entries via
    mutators.read_foam_entry before this capability existed. Activation: a
    plugin has no get_config_value_reader hook. Plan 2 seam: a non-OpenFOAM
    plugin must implement the hook explicitly -- this fallback assumes
    OpenFOAM syntax and is not a safe default for other environments."""

    from omnidriver.openfoam.mutators import read_foam_entry

    return read_foam_entry(path, key)


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
