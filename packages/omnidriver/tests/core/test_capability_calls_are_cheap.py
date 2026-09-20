"""Capability accessors must be cheap enough to call at context construction.

Phase 1's stack digest materializes capabilities when a DriverContext is
built. An accessor that re-parses YAML from package resources on every call
makes that too slow to do. Phase 0 Task 12 caches the three accessors an
audit found doing that: cardiacCore's guidance manifest, cardiacFoam's
runtime backend contract, and core's own capability-manifest adapter.
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
    """The cache holds the parsed document; callers must not be able to
    mutate it through what `describe_guidance` returns.

    `_load_manifest` is process-wide (``lru_cache``); if `describe_guidance`
    stopped deep-copying before returning, one caller mutating a nested
    ``roles`` entry would corrupt every other caller's view for the rest of
    the process.
    """
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore import agent_guidance

    first = agent_guidance.describe_guidance()
    role = next(iter(first["roles"]))
    first["roles"][role]["resource"] = "corrupted"

    second = agent_guidance.describe_guidance()
    assert second["roles"][role]["resource"] != "corrupted"


def test_profile_contract_reuses_the_cached_profile_parse():
    """`_profile_contract` must not independently re-read `plugin.yaml`.

    `CardiacFoamPlugin.get_profile()` already parses and caches the file;
    `_profile_contract` reusing `PluginProfile.payload` also means the
    `runtime.backend` contract it returns is now provably the same object
    backing the rest of the profile (and its `digest`), not a second,
    independently-read copy of the same file.
    """
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
    from omnidriver.cardiacfoam.runtime_profile import _profile_contract

    profile = CardiacFoamPlugin.get_profile()
    contract = _profile_contract()

    assert contract is profile.payload["runtime"]["backend"]


def test_capability_manifest_adapter_caches_per_instance():
    """`_CapabilityManifestAdapter` memoizes per adapter instance, not
    globally.

    `adapt_plugin_capabilities` builds one adapter per `DriverContext`. A
    module-level cache would leak one context's manifest into another's;
    caching on the (frozen) adapter instance instead means the same adapter
    called twice returns the exact object it built the first time, while a
    different adapter -- a different context -- starts fresh.
    """
    from omnidriver.core.plugin_capabilities import _CapabilityManifestAdapter
    from plugins.minimal_plugin import MinimalTestPlugin

    adapter = _CapabilityManifestAdapter(MinimalTestPlugin())
    first = adapter.manifest()
    second = adapter.manifest()
    assert first is second

    other_adapter = _CapabilityManifestAdapter(MinimalTestPlugin())
    assert other_adapter.manifest() is not first
