"""Capability accessors must be cheap enough to call at context construction.

Phase 1's stack digest materializes capabilities when a DriverContext is
built. An accessor that re-parses YAML from package resources on every call
makes that too slow to do. Phase 0 Task 12 caches the three accessors an
audit found doing that: cardiacCore's guidance manifest, cardiacFoam's
runtime backend contract, and core's own capability-manifest adapter.

**Corrected 2026-09-22 (Task 10):** the third of those three is no longer
cached. Task 10 moved capability-manifest ASSEMBLY into core itself (reading
the composed ``command_authorization``/``case_introspection``/
``case_runtime_conventions`` capabilities plus a plugin's own small domain
dict), which is a handful of in-memory reads, not a re-parse -- so the
"cheap enough to call repeatedly" property this module guards no longer
needs a cache to hold. Caching it instead meant every `.manifest()` caller
sharing one `DriverContext` (`dict_entries`, `strict_planning`,
`introspection`) shared the exact same assembled dict, narrowing the
isolation `DriverContext` exists to provide (Phase 0 review, 2026-09-20).
See `plugin_capabilities._CapabilityManifestAdapter` for the removal.
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


def test_capability_manifest_adapter_no_longer_shares_a_cached_copy():
    """`_CapabilityManifestAdapter` no longer memoizes -- on purpose.

    **Corrected 2026-09-22 (Task 10):** this test used to be named
    `test_capability_manifest_adapter_caches_per_instance` and asserted the
    opposite (`first is second`). That cache -- introduced by Phase 0 Task
    12 to avoid recomputing an expensive plugin-authored manifest -- meant
    every `.manifest()` call on one adapter (i.e. every caller sharing one
    `DriverContext`, since `DriverContext.capabilities` is itself cached)
    got back the exact same dict, including its nested, plugin-owned
    sub-dicts. Nothing mutated it, but that narrowed the very isolation
    `DriverContext` exists to provide. Now that assembly reads a handful of
    cheap composed capabilities instead of doing the plugin's own expensive
    work, there is nothing left to cache, and this asserts the opposite: two
    calls return equal but independent objects.
    """
    from omnidriver.core.plugin_capabilities import _CapabilityManifestAdapter
    from plugins.minimal_plugin import MinimalTestPlugin

    adapter = _CapabilityManifestAdapter(MinimalTestPlugin())
    first = adapter.manifest()
    second = adapter.manifest()
    assert first == second
    assert first is not second
