from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import (
    SUPPORTED_PLUGIN_API_VERSIONS,
    driver_context
)
from plugins.toy import ToyProvider


def test_supported_version_is_three() -> None:
    assert SUPPORTED_PLUGIN_API_VERSIONS == frozenset({"3"})


def test_neutral_plugin_is_v3() -> None:
    # StackIdentity has no singular api_version -- one per provider, on
    # StackIdentity.providers (a tuple of ProviderIdentity). A single-plugin
    # driver_context composes to a one-entry stack.
    context = driver_context(ToyProvider(), source="test:plugin-api")
    assert context.identity.providers[0].api_version == "3"


@pytest.mark.parametrize("version", ["2", "99"])
def test_unsupported_version_is_rejected_before_any_catalog_runs(version) -> None:
    class FuturePlugin(ToyProvider):
        @property
        def plugin_api_version(self) -> str:
            return version

        def get_dict_entries(self):
            raise AssertionError("must be rejected before catalogs are read")

        def get_profile(self):
            raise AssertionError("must be rejected before the profile is read")

    with pytest.raises(TypeError, match=f"{version!r} is not supported"):
        driver_context(FuturePlugin(), source="test")


def test_neutral_plugin_builds_an_explicit_context() -> None:
    context = driver_context(ToyProvider(), source="test:plugin-api")
    assert context.identity.providers[0].id == "org.omnidriver.test-minimal"
