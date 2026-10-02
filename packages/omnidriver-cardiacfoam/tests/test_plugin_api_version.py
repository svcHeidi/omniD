"""The cardiac plugin's half of the plugin-API-version contract; the generic half is in core."""

from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def test_cardiacfoam_plugin_is_v2() -> None:
    assert CardiacFoamPlugin().plugin_api_version == "2"


def test_cardiacfoam_plugin_satisfies_the_full_protocol() -> None:
    """`validate_plugin`, not `isinstance(SolverPlugin)`: the environment hooks come from the provider."""
    from omnidriver.core.plugin_interface import validate_plugin

    validate_plugin(CardiacFoamPlugin())  # must not raise
