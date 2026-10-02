"""Capability accessors must be cheap enough to call at context construction."""

import pytest


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
