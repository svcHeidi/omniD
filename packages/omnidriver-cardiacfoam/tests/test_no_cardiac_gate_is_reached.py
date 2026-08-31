"""No compatibility fallback may answer in cardiac terms for the cardiac plugin.

core/compatibility.py used to have twenty branches gated on
plugin_id == "org.cardiacfoam". Each existed only for plugins predating an
optional hook; once CardiacFoamPlugin implemented every hook, the adapter
called it directly and the gate was dead code. Phase 2 Task 7 measured that
the census below still passed (proving the deletion was safe) and then
deleted all twenty branches.

This module now guards the result of that deletion, two ways:
  1. the gated set must stay empty -- a plugin_id == "org.cardiacfoam" branch
     reappearing anywhere in compatibility.py is a regression, not a new
     optimization;
  2. the standing behavioural check -- reading capabilities under an explicit
     cardiac context must fire no gated fallback -- keeps running, since it
     is a fact worth continuing to prove even with the gated set at zero.
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


def test_no_gated_fallback_exists() -> None:
    """Phase 2 Task 7 deleted the twenty cardiac-gated branches. A new one
    appearing -- even a single one -- is a regression worth noticing."""
    assert _gated_fallback_names() == frozenset()


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
