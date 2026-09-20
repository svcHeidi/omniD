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
    assert driver_context(
        MinimalTestPlugin(), source="test:plugin-api",
    ).identity.api_version == "2"


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


def test_declaring_the_contract_without_implementing_it_is_rejected() -> None:
    """A version string is not a contract unless the shape is checked. Without
    this, a plugin claiming to speak the contract while missing a required
    member would fail only much later, deep inside whichever core module
    first called the missing method."""

    class HalfMigratedPlugin(MinimalTestPlugin):
        # Drops one required member. Must be a member the seam tiers still
        # mark `required` -- Task 4 (2026-09-20) demoted thirteen members
        # (including the former `get_artifact_value_reader`) to
        # `optional-neutral`, so a plugin lacking one of those is no longer
        # rejected here.
        get_dictionary_catalog = None

    with pytest.raises(TypeError, match="does not implement the plugin contract"):
        driver_context(HalfMigratedPlugin(), source="test")


def test_the_shape_check_names_what_is_missing() -> None:
    # Both members must be `required` per the seam tiers -- see the note in
    # test_declaring_the_contract_without_implementing_it_is_rejected above.
    class MissingTwo(MinimalTestPlugin):
        get_dict_groups = None
        get_tutorial_catalog = None

    with pytest.raises(TypeError) as excinfo:
        driver_context(MissingTwo(), source="test")
    message = str(excinfo.value)
    assert "get_dict_groups" in message
    assert "get_tutorial_catalog" in message


def test_neutral_plugin_builds_an_explicit_context() -> None:
    context = driver_context(MinimalTestPlugin(), source="test:plugin-api")
    assert context.identity.id == "org.driverfoam.test-minimal"
