"""A plugin's dictionary phases are its own, not cardiacFoam's four."""
from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.specs.validation import primary_phase
from plugins.minimal_plugin import MinimalTestPlugin


class _Entry:
    def __init__(self, phases):
        self.phases = phases
        self.driver_path = "some/path"


def test_primary_phase_uses_the_order_it_is_given() -> None:
    entry = _Entry(("solve", "setup"))
    assert primary_phase(entry, ("setup", "solve")) == "setup"
    assert primary_phase(entry, ("solve", "setup")) == "solve"


def test_an_entry_claiming_no_declared_phase_returns_none() -> None:
    assert primary_phase(_Entry(("mesh",)), ("setup", "solve")) is None


def test_the_generic_plugin_declares_the_phases_its_entries_use() -> None:
    """It has no entries, so it declares no phases -- and must not inherit cardiacFoam's four."""
    phases = driver_context(
        MinimalTestPlugin(), source="test:neutral-phases",
    ).capabilities.dictionaries.phases()
    assert phases == ()
