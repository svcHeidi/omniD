"""No compatibility fallback may answer in cardiac terms for the cardiac plugin.

core/compatibility.py has twenty branches gated on
plugin_id == "org.cardiacfoam". Each exists only for plugins predating an
optional hook. Once CardiacFoamPlugin implements the hook, the adapter calls it
directly and the gate is dead code.

This asserts that directly: run an operation under an explicit cardiac context
and assert no gated fallback fired. Phase 2 deletes the branches; this is the
evidence that deleting them is safe.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


def _gated_fallback_names() -> frozenset[str]:
    """Every legacy_* whose source branches on the cardiac plugin id."""
    names = set()
    for name in dir(compatibility):
        if not name.startswith("legacy_"):
            continue
        func = getattr(compatibility, name)
        if not callable(func):
            continue
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        if "org.cardiacfoam" in source:
            names.add(name)
    return frozenset(names)


def test_the_gate_set_is_the_twenty_we_measured() -> None:
    """A twenty-first gate appearing is a regression worth noticing."""
    assert len(_gated_fallback_names()) == 20


def test_reading_every_capability_under_cardiac_fires_no_gated_fallback() -> None:
    gated = _gated_fallback_names()
    context = driver_context(CardiacFoamPlugin(), source="test:cardiac-census")

    with compatibility.track_fallback_calls() as calls:
        caps = context.capabilities
        caps.case_files.describe_config_resolution()
        caps.report_catalog.reports()
        caps.named_catalogs.catalogs()
        caps.override_scopes.scopes()
        caps.dict_regeneration.scopes()
        caps.command_authorization.solver_commands()
        caps.command_authorization.auxiliary_commands()
        caps.command_authorization.utility_manifests()
        caps.command_authorization.utility_roots()
        caps.case_introspection.samplable_fields({})
        caps.case_introspection.resolve_case_models(Path("/nonexistent"))
        fired = sorted({name for name in calls if name in gated})

    assert fired == [], (
        f"gated cardiac fallbacks fired under an explicit cardiac context: "
        f"{fired}. Each names a hook CardiacFoamPlugin should implement."
    )
