"""An explicitly-contexted operation must never fall back to the cardiac default."""
from __future__ import annotations

import json

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.sweep_runner import sweep_plan

import plugins.minimal_plugin as minimal_plugin
from plugins.sweepable_plugin import SweepablePlugin


def assert_no_default_context_fallback(operation) -> None:
    with compatibility.track_fallback_calls() as calls:
        operation()
        fired = [n for n in calls if n == "absent_default_driver_context"]
    assert fired == [], (
        f"operation resolved the built-in cardiac context {len(fired)} time(s); "
        "it should use the DriverContext it was given"
    )


def test_capability_reads_under_an_explicit_generic_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalTestPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.dictionaries.groups()
        caps.manifest.manifest()
        caps.generic_case_factory.factory()

    assert_no_default_context_fallback(op)


def test_capability_reads_under_an_explicit_minimal_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalTestPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.case_files.required_files()

    assert_no_default_context_fallback(op)


def test_a_generic_sweep_plan_under_an_explicit_context_uses_no_default(tmp_path):
    """sweep_plan must materialize through the plugin it was handed."""
    ctx = driver_context(SweepablePlugin(), source="test:census-sweep")
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
