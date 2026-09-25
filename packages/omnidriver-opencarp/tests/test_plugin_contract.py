from __future__ import annotations

from omnidriver.core.plugin_discovery import load_discovered_plugin


def test_opencarp_stack_is_one_provider_C1():
    ctx = load_discovered_plugin("opencarp")
    assert [p.plugin_id for p in ctx.providers] == ["org.omnidriver.opencarp"]


def test_record_is_registered():
    ctx = load_discovered_plugin("opencarp")
    assert "niedererNVersion" in ctx.capabilities.tutorial_records.catalog()
