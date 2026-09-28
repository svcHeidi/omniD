"""The shipped plugin resolves through real installed metadata. It deliberately does not
monkeypatch ``plugin_discovery._entry_points()``, since mocked discovery never reads ENTRY_POINT_GROUP."""
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
    # cardiacFoam requires the OpenFOAM environment provider, which `load_plugin_context`
    # composes in; cardiacFoam is the most specific, last in the ordered stack.
    primary = context.identity.to_json()["providers"][-1]
    assert primary["id"] == "org.cardiacfoam"
    assert primary["source"].startswith("entry-point:omnidriver-cardiacfoam=")
