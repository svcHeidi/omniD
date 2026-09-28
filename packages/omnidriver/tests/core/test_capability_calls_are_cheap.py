"""Capability accessors must be cheap enough to call at context construction.

Guards the accessors that cache an expensive parse instead of re-reading it
on every call: cardiacCore's guidance manifest, cardiacFoam's runtime backend
contract.
"""

import pytest


def test_named_catalogs_does_not_reparse_on_every_call():
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore import agent_guidance

    first = agent_guidance.describe_guidance()
    second = agent_guidance.describe_guidance()
    assert first == second
    assert agent_guidance._load_manifest.cache_info().hits >= 1


def test_describe_guidance_never_hands_out_the_cached_manifest_itself():
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore import agent_guidance

    first = agent_guidance.describe_guidance()
    role = next(iter(first["roles"]))
    first["roles"][role]["resource"] = "corrupted"

    second = agent_guidance.describe_guidance()
    assert second["roles"][role]["resource"] != "corrupted"


def test_profile_contract_reuses_the_cached_profile_parse():
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.cardiacfoam.runtime_profile import _profile_contract

    profile = CardiacFoamPlugin.get_profile()
    contract = _profile_contract()

    assert contract is profile.payload["runtime"]["backend"]


def test_capability_manifest_adapter_no_longer_shares_a_cached_copy():
    from omnidriver.core.plugin_capabilities import _CapabilityManifestAdapter
    from plugins.minimal_plugin import MinimalTestPlugin

    adapter = _CapabilityManifestAdapter(MinimalTestPlugin())
    first = adapter.manifest()
    second = adapter.manifest()
    assert first == second
    assert first is not second
