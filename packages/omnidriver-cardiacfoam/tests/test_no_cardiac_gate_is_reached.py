"""No compatibility fallback may answer in cardiac terms for the cardiac plugin.

No ``absent_*`` fallback in ``core.compatibility`` may branch on ``"org.cardiacfoam"``, and none fires under a cardiac context.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


def _gated_fallback_names() -> frozenset[str]:
    """Every absent_* whose source branches on the cardiac plugin id."""
    names = set()
    for name in dir(compatibility):
        if not name.startswith("absent_"):
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
    assert _gated_fallback_names() == frozenset()


def test_reading_every_capability_under_cardiac_fires_no_gated_fallback() -> None:
    gated = _gated_fallback_names()
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:cardiac-census")

    with compatibility.track_fallback_calls() as calls:
        caps = context.capabilities
        caps.case_files.all_rules()
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
