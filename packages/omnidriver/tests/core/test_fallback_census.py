"""Explicitly-contexted operations never resolve a default plugin.

The static guard in test_core_context_is_explicit.py proves core contains no
implicit resolution syntactically. This proves the runtime consequence: an
operation driven by a named plugin fires legacy_default_driver_context zero
times.
"""
from __future__ import annotations

import json

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.sweep_runner import sweep_plan

import plugins.minimal_plugin as minimal_plugin
from plugins.declared_case_plugin import DeclaredCasePlugin


def assert_no_default_context_fallback(operation) -> None:
    with compatibility.track_fallback_calls() as calls:
        operation()
        fired = [n for n in calls if n == "legacy_default_driver_context"]
    assert fired == [], (
        f"operation resolved a default plugin context {len(fired)} time(s); "
        "it should use the DriverContext it was given"
    )


def test_capability_reads_under_an_explicit_generic_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalTestPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.dictionaries.groups()
        caps.manifest.manifest()
        caps.tutorials.displays()

    assert_no_default_context_fallback(op)


def test_capability_reads_under_an_explicit_minimal_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalTestPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.case_files.required_files()

    assert_no_default_context_fallback(op)


class _SweepablePlugin(DeclaredCasePlugin):
    """A non-cardiac plugin implementing both sweep hooks.

    The base supplies only the declared entrypoint, output root, and no-op
    preflight that this sweep reaches before its own routing hooks run.
    """

    def route_sweep_case_values(self, *, base, resolved_axis_values, driver_context):
        return {**base, **resolved_axis_values}

    def materialize_sweep_case(self, *, case_dir, routed):
        # Write the declared case script so sweep_plan's strict-plan step can
        # resolve the materialized folder. A materializer that only mkdir'd would make the operation
        # fail downstream for reasons unrelated to context threading, and a
        # census that stops early observes fewer fallbacks than it claims to.
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "run-test-case").write_text("#!/bin/sh\n")


def test_a_generic_sweep_plan_under_an_explicit_context_uses_no_default(tmp_path):
    """sweep_plan must materialize through the plugin it was handed.

    The capability reads above never enter the sweep path, which is how
    sweep_runner.py:273/:449 dropped their context unnoticed: they called
    the public-edge ``materialize_case`` without threading ``driver_context``,
    so every generic sweep case was written by cardiacFoam's materializer no
    matter which plugin drove the sweep.
    """
    ctx = driver_context(_SweepablePlugin(), source="test:census-sweep")
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps({
        "base": {},
        "sweep": {"mode": "zip", "independent": {"axisA": ["valueA", "valueB"]}},
    }))

    report: dict = {}

    def op() -> None:
        report.update(sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx))

    assert_no_default_context_fallback(op)
    # A census over an operation that silently produced nothing proves
    # nothing. Both cases must actually have been routed and materialized.
    assert report["case_count"] == 2
    assert [case["status"] for case in report["cases"]] == ["ok", "ok"]
