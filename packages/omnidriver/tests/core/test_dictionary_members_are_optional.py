"""A solver without dictionaries (openCARP, the toy) implements none of the
dictionary members, and loads, describes and runs."""
from __future__ import annotations

import pytest

from omnidriver.conformance import run_check
from omnidriver.core import provider_stack
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_interface import driver_context
from plugins.toy import toy_conformance_target
from plugins.toy import ToyStack
from plugins.toy import ToyProvider

_NOW_OPTIONAL = ("get_dict_entries", "get_dictionary_catalog")


@pytest.mark.parametrize("member", _NOW_OPTIONAL)
def test_the_toy_implements_none_of_them(member):
    """Non-vacuity: the proofs below drive a plugin that really lacks them."""
    assert not callable(getattr(ToyStack(), member, None))


def test_a_plugin_without_them_loads_and_composes_to_empty_answers():
    ctx = driver_context(ToyProvider(), source="test")
    assert ctx.stack.call("get_dict_entries") == ()
    assert dict(ctx.stack.call("get_dictionary_catalog").documents) == {}


@pytest.mark.parametrize("check_id", ["C1", "C2", "C6", "C10"])
def test_a_plugin_without_them_loads_describes_and_runs(check_id, tmp_path):
    verdict = run_check(check_id, toy_conformance_target(tmp_path))
    assert verdict.status == ("not_applicable" if check_id == "C2" else "passed"), verdict.detail


class _EmptyStubs(ToyProvider):
    """Dictionary members that answer empty."""

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})


def test_no_dictionary_entries_digests_exactly_as_an_empty_stub_did():
    absent = driver_context(ToyProvider(), source="test").identity.providers[0].provider_digest
    stubbed = driver_context(_EmptyStubs(), source="test").identity.providers[0].provider_digest
    assert absent == stubbed


def test_a_stack_with_no_dictionary_implementer_records_the_member_unclaimed():
    assert driver_context(ToyProvider(), source="test").identity.resolutions["get_dict_entries"] == provider_stack.UNCLAIMED
    assert driver_context(_EmptyStubs(), source="test").identity.resolutions["get_dict_entries"] == "org.omnidriver.test-minimal"
