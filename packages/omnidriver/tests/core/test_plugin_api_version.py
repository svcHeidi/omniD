from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import (
    SUPPORTED_PLUGIN_API_VERSIONS,
    driver_context
)
from plugins.minimal_plugin import MinimalTestPlugin


def test_supported_version_is_two() -> None:
    assert SUPPORTED_PLUGIN_API_VERSIONS == frozenset({"2"})


def test_neutral_plugin_is_v2() -> None:
    # StackIdentity has no singular api_version -- one per provider, on
    # StackIdentity.providers (a tuple of ProviderIdentity). A single-plugin
    # driver_context composes to a one-entry stack.
    context = driver_context(MinimalTestPlugin(), source="test:plugin-api")
    assert context.identity.providers[0].api_version == "2"


def test_unsupported_version_is_rejected_before_any_catalog_runs() -> None:
    class FuturePlugin(MinimalTestPlugin):
        @property
        def plugin_api_version(self) -> str:
            return "99"

        def get_dict_entries(self):
            raise AssertionError("must be rejected before catalogs are read")

        def get_profile(self):
            raise AssertionError("must be rejected before the profile is read")

    with pytest.raises(TypeError, match="99"):
        driver_context(FuturePlugin(), source="test")


def test_neutral_plugin_builds_an_explicit_context() -> None:
    context = driver_context(MinimalTestPlugin(), source="test:plugin-api")
    assert context.identity.providers[0].id == "org.omnidriver.test-minimal"
