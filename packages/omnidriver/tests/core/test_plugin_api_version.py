from __future__ import annotations

import pytest

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_interface import (
    SUPPORTED_PLUGIN_API_VERSIONS,
    driver_context,
    generic_openfoam_context,
)


def test_supported_version_is_two() -> None:
    assert SUPPORTED_PLUGIN_API_VERSIONS == frozenset({"2"})


def test_generic_builtin_plugin_is_v2() -> None:
    """Half of what was test_builtin_plugins_are_v2; the cardiac half moved
    to omnidriver-cardiacfoam's tests/test_plugin_api_version.py as
    CardiacFoamPlugin().plugin_api_version == "2"."""
    assert generic_openfoam_context().identity.api_version == "2"


def test_unsupported_version_is_rejected_before_any_catalog_runs() -> None:
    class FuturePlugin(GenericOpenFOAMPlugin):
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

    class HalfMigratedPlugin(GenericOpenFOAMPlugin):
        # Drops one required member.
        get_artifact_value_reader = None

    with pytest.raises(TypeError, match="does not implement the plugin contract"):
        driver_context(HalfMigratedPlugin(), source="test")


def test_the_shape_check_names_what_is_missing() -> None:
    class MissingTwo(GenericOpenFOAMPlugin):
        get_solve_step_commands = None
        get_utility_roots = None

    with pytest.raises(TypeError) as excinfo:
        driver_context(MissingTwo(), source="test")
    message = str(excinfo.value)
    assert "get_solve_step_commands" in message
    assert "get_utility_roots" in message


def test_generic_builtin_plugin_satisfies_the_full_protocol() -> None:
    """Half of what was test_both_builtin_plugins_satisfy_the_full_protocol:
    cardiac AND generic must each exercise every required capability -- this
    test previously caught the generic plugin declaring v2 while
    implementing only 8 of 12, riding the adapter's degrade-to-empty
    fallback. The cardiac half moved to omnidriver-cardiacfoam's
    tests/test_plugin_api_version.py, preserving that same intent there."""
    from omnidriver.core.plugin_interface import SolverPlugin

    assert isinstance(GenericOpenFOAMPlugin(), SolverPlugin)
