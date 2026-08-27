"""The shipped plugin resolves through real installed metadata.

Deliberately does NOT monkeypatch plugin_discovery._entry_points(). That seam
exists so unit tests need no pip install, and it is exactly why a group-name
mismatch survived a package rename: mocked discovery never reads
ENTRY_POINT_GROUP. This test does.
"""
from __future__ import annotations

from importlib.metadata import entry_points

from omnidriver.core.plugin_discovery import ENTRY_POINT_GROUP, discover_plugins
from omnidriver.core.plugin_interface import load_plugin_context


def test_cardiacfoam_is_registered_in_the_group_core_reads() -> None:
    names = {ep.name for ep in entry_points(group=ENTRY_POINT_GROUP)}
    assert "cardiacfoam" in names, (
        f"installed distributions register {sorted(names)} in group "
        f"{ENTRY_POINT_GROUP!r}; 'cardiacfoam' is missing"
    )


def test_cardiacfoam_loads_by_discovered_name() -> None:
    assert "cardiacfoam" in discover_plugins()
    context = load_plugin_context("cardiacfoam")
    assert context.identity.id == "org.cardiacfoam"
    assert context.identity.source.startswith("entry-point:omnidriver-cardiacfoam=")
