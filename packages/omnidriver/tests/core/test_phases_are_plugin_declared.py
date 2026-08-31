"""A plugin's dictionary phases are its own, not cardiacFoam's four.

core's Phase literal spells anatomy/physics/stimulus/solver. While
primary_phase() walked that literal, every entry of a plugin using different
phase words returned None -- and validation's required-field and enum checks
both read None as "skip". A plugin got a clean bill of health because core
could not see its entries at all. That is the only silently-wrong defect in
the compatibility set.
"""
from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context
from omnidriver.core.specs.validation import primary_phase


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
    """It has no entries, so it declares no phases -- and must not inherit
    cardiacFoam's four."""
    phases = generic_openfoam_context().capabilities.dictionaries.phases()
    assert phases == ()


def test_cardiacfoam_declares_its_four_in_order() -> None:
    import pytest

    cardiacfoam_plugin = pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason="omnidriver-cardiacfoam is not installed",
    )
    context = driver_context(
        cardiacfoam_plugin.CardiacFoamPlugin(), source="test:phases",
    )
    assert context.capabilities.dictionaries.phases() == (
        "anatomy", "physics", "stimulus", "solver",
    )
