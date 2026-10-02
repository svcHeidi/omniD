from __future__ import annotations

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.core.plugin_interface import (
    driver_context,
    validate_plugin,
)
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


def test_cardiacfoam_plugin_satisfies_runtime_contract() -> None:
    plugin = validate_plugin(CardiacFoamPlugin())
    ctx = driver_context(OpenFOAMEnvironmentPlugin(), plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.cardiacfoam"
    assert plugin.plugin_name == "cardiacFoam"
    assert plugin.get_dict_entries()
    assert {"deltaT", "endTime"} <= {
        entry.driver_path
        for entry in plugin.get_dictionary_catalog().documents["controlDict"]
    }


def test_generic_openfoam_plugin_satisfies_runtime_contract() -> None:
    plugin = validate_plugin(OpenFOAMEnvironmentPlugin())
    ctx = driver_context(plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.openfoam.environment"
    assert ctx.stack.call("get_dict_entries") == ()

