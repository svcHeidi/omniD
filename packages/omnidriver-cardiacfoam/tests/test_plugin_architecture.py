from __future__ import annotations

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.core.plugin_interface import (
    driver_context,
    validate_plugin,
)
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def test_cardiacfoam_plugin_satisfies_runtime_contract() -> None:
    plugin = validate_plugin(CardiacFoamPlugin())
    # Not `isinstance(plugin, SolverPlugin)`: the Protocol lists environment
    # hooks this plugin composes from the environment provider instead.
    # `validate_plugin` is the real gate (required members from `:status:` tiers).
    ctx = driver_context(OpenFOAMEnvironmentPlugin(), plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.cardiacfoam"
    assert plugin.plugin_name == "cardiacFoam"
    assert plugin.get_dict_entries()
    assert callable(plugin.get_generic_case_factory())
    assert {"deltaT", "endTime"} <= {
        entry.driver_path
        for entry in plugin.get_dictionary_catalog().documents["controlDict"]
    }


def test_generic_openfoam_plugin_satisfies_runtime_contract() -> None:
    plugin = validate_plugin(OpenFOAMEnvironmentPlugin())
    ctx = driver_context(plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.openfoam.environment"
    assert ctx.capabilities.dictionaries.entries() == ()
    assert not hasattr(plugin, "get_generic_case_factory")


def test_minimal_plugin_proves_non_cardiac_solver_contract() -> None:
    plugin = validate_plugin(MinimalOpenFOAMPlugin())
    ctx = driver_context(plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.test-minimal"
    assert ctx.capabilities.dictionaries.entries() == ()
    assert plugin.get_capabilities() == {}
