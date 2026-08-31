"""An explicitly-contexted operation must never fall back to the cardiac default.

The static guard in test_core_context_is_explicit.py proves core contains no
implicit resolution syntactically. This proves the runtime consequence: an
operation driven by a named plugin fires legacy_default_driver_context zero
times.

Note: `caps.dictionaries.phases()` from the plan's Task 5 Step 4 template is
omitted here. That method does not exist yet -- it ships with Task 3
(`get_phases()`), which has not landed on this branch.
"""
from __future__ import annotations

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context

import plugins.minimal_plugin as minimal_plugin


def assert_no_default_context_fallback(operation) -> None:
    with compatibility.track_fallback_calls() as calls:
        operation()
        fired = [n for n in calls if n == "legacy_default_driver_context"]
    assert fired == [], (
        f"operation resolved the built-in cardiac context {len(fired)} time(s); "
        "it should use the DriverContext it was given"
    )


def test_capability_reads_under_an_explicit_generic_context_use_no_default() -> None:
    ctx = generic_openfoam_context()

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.dictionaries.groups()
        caps.manifest.manifest()
        caps.tutorials.displays()

    assert_no_default_context_fallback(op)


def test_capability_reads_under_an_explicit_minimal_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalOpenFOAMPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.case_files.required_files()

    assert_no_default_context_fallback(op)
