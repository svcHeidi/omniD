"""The dictionary-shaped members are optional-neutral
(spec 2026-09-26-core-generality-design.md §2, A3)."""
from __future__ import annotations

import pytest

from omnidriver.conformance import run_check
from omnidriver.core import provider_stack
from omnidriver.core.capability_seams import members_by_tier
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_interface import driver_context
from plugins.conformance_toy import toy_conformance_target
from plugins.e2e_record_plugin import E2ERecordPlugin
from plugins.minimal_plugin import MinimalTestPlugin

_NOW_OPTIONAL = ("get_dict_entries", "get_dict_groups", "get_dictionary_catalog", "get_tutorial_displays")


def test_the_four_are_optional_neutral_and_the_tutorial_catalog_stays_required():
    tiers = members_by_tier()
    assert set(_NOW_OPTIONAL) <= tiers["optional-neutral"]
    assert "get_tutorial_catalog" in tiers["required"]


@pytest.mark.parametrize("member", _NOW_OPTIONAL)
def test_the_toy_implements_none_of_them(member):
    """Non-vacuity: the proofs below drive a plugin that really lacks them."""
    assert not callable(getattr(E2ERecordPlugin(), member, None))


def test_a_plugin_without_them_loads_and_composes_to_empty_answers():
    ctx = driver_context(MinimalTestPlugin(), source="test")
    assert ctx.capabilities.dictionaries.entries() == ()
    assert ctx.capabilities.dictionaries.groups() == {}
    assert dict(ctx.capabilities.dictionaries.catalog().documents) == {}
    assert ctx.capabilities.dictionaries.phases() == ()
    assert ctx.capabilities.tutorials.displays() == ()


@pytest.mark.parametrize("check_id", ["C1", "C2", "C6", "C10"])
def test_a_plugin_without_them_loads_describes_and_runs(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.passed, verdict.detail


class _EmptyStubs(MinimalTestPlugin):
    """The stubs as the openfoam and opencarp plugins carried them before A3."""

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})

    def get_dict_groups(self):
        return {}

    def get_tutorial_displays(self):
        return ()


def test_no_dictionary_entries_digests_exactly_as_an_empty_stub_did():
    absent = driver_context(MinimalTestPlugin(), source="test").identity.providers[0].provider_digest
    stubbed = driver_context(_EmptyStubs(), source="test").identity.providers[0].provider_digest
    assert absent == stubbed


def test_a_stack_with_no_dictionary_implementer_records_the_capability_unclaimed():
    assert driver_context(MinimalTestPlugin(), source="test").identity.resolutions["dictionaries"] == provider_stack.UNCLAIMED
    assert driver_context(_EmptyStubs(), source="test").identity.resolutions["dictionaries"] == "org.driverfoam.test-minimal"
