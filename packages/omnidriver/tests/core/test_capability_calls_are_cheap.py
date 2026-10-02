"""Capability accessors must be cheap enough to call at context construction."""

import pytest


def test_profile_contract_reuses_the_cached_profile_parse():
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.cardiacfoam.runtime_profile import _profile_contract

    profile = CardiacFoamPlugin.get_profile()
    contract = _profile_contract()

    assert contract is profile.payload["runtime"]["backend"]


def test_the_capability_manifest_is_never_a_shared_copy():
    from omnidriver.core.capability_manifest import capability_manifest
    from omnidriver.core.plugin_interface import driver_context
    from plugins.toy import ToyProvider

    context = driver_context(ToyProvider(), source="test")
    first = capability_manifest(context)
    second = capability_manifest(context)
    assert first == second
    assert first is not second
