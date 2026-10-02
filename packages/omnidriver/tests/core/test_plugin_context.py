from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from omnidriver.core.plugin_interface import (
    driver_context,
    validate_plugin,
)
from omnidriver.core.contracts.dictionary import DictEntry


class _Plugin:
    def __init__(self, plugin_id: str, tutorial_name: str) -> None:
        self._plugin_id = plugin_id
        self._tutorial_name = tutorial_name

    @property
    def plugin_name(self) -> str:
        return self._plugin_id

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def plugin_version(self) -> str:
        return "1.0.0"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    def get_dict_entry_catalog(self):
        # A per-instance-distinguishable answer: proves context isolation.
        return {self._tutorial_name: ()}


def _named_factory(context) -> str:
    (name,) = context.stack.call("get_dict_entry_catalog")
    return name


def test_contexts_do_not_share_plugin_selection() -> None:
    alpha = driver_context(_Plugin("example.alpha", "alpha"), source="test")
    beta = driver_context(_Plugin("example.beta", "beta"), source="test")

    assert _named_factory(alpha) == "alpha"
    assert _named_factory(beta) == "beta"
    # StackIdentity.to_json() has no singular "id" -- one provider per entry
    # in "providers". Each of these contexts composes a one-provider stack.
    assert alpha.identity.to_json()["providers"][0]["id"] == "example.alpha"
    assert beta.identity.to_json()["providers"][0]["id"] == "example.beta"


def test_plugin_contexts_remain_isolated_sequentially_and_concurrently() -> None:
    contexts = (
        driver_context(_Plugin("example.alpha", "alpha"), source="test"),
        driver_context(_Plugin("example.beta", "beta"), source="test"),
        # Distinct neutral plugin instances prove that neither selection nor
        # catalog state leaks across threads; this contract needs no adapter.
        driver_context(_Plugin("example.gamma", "gamma"), source="test"),
        driver_context(_Plugin("example.delta", "delta"), source="test"),
    )
    expected = ("alpha", "beta", "gamma", "delta")

    assert tuple(_named_factory(context) for context in contexts) == expected
    with ThreadPoolExecutor(max_workers=len(contexts)) as executor:
        futures = [executor.submit(_named_factory, context) for context in contexts]
    assert tuple(future.result() for future in futures) == expected


def test_plugin_contract_rejects_missing_members() -> None:
    with pytest.raises(TypeError, match="missing required members"):
        validate_plugin(object())


def test_plugin_contract_rejects_an_invalid_stable_id() -> None:
    with pytest.raises(TypeError, match="plugin_id must use lowercase"):
        validate_plugin(_Plugin("Example Plugin", "example"))


def test_driver_context_rejects_duplicate_catalog_paths() -> None:
    plugin = _Plugin("example.duplicates", "duplicates")
    plugin.get_dict_entries = lambda: (
        DictEntry(driver_path="shared", description="first", value_kind="word"),
        DictEntry(driver_path="shared", description="second", value_kind="word"),
    )

    with pytest.raises(TypeError, match="duplicate paths: shared"):
        driver_context(plugin, source="test")


def test_context_identity_binds_resolved_manifest_and_dictionary_vocabulary() -> None:
    plugin = _Plugin("example.identity", "identity")
    baseline = driver_context(plugin, source="test").identity.capability_digest

    plugin.get_capabilities = lambda: {"accepted": ["utilityA"]}
    manifest_changed = driver_context(plugin, source="test").identity.capability_digest
    plugin.get_dict_entries = lambda: (
        DictEntry(
            driver_path="system/controlDict:endTime", description="end time",
            value_kind="scalar",
        ),
    )
    vocabulary_changed = driver_context(plugin, source="test").identity.capability_digest

    assert baseline != manifest_changed != vocabulary_changed
