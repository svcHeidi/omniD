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
    # NOT `isinstance(plugin, SolverPlugin)` (Task 9): `SolverPlugin` lists
    # `get_environment_commands`/`is_installed_environment_command` as
    # Protocol members, so Python's structural `isinstance` demands them of
    # this ONE class -- but this plugin now composes those from the
    # environment provider rather than embedding them, exactly what Task 9
    # set out to do. `validate_plugin` (called above, would have raised) is
    # the real gate, and it derives required members from the capability
    # seams' `:status:` tiers, where both those hooks are optional-neutral.
    ctx = driver_context(OpenFOAMEnvironmentPlugin(), plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.cardiacfoam"
    assert plugin.plugin_name == "cardiacFoam"
    assert plugin.get_dict_entries()
    assert "registered_tutorials" in plugin.get_tutorial_catalog()
    assert "spec_factories" in plugin.get_tutorial_catalog()
    assert {"deltaT", "endTime"} <= {
        entry.driver_path
        for entry in plugin.get_dictionary_catalog().documents["controlDict"]
    }


def test_generic_openfoam_plugin_satisfies_runtime_contract() -> None:
    plugin = validate_plugin(OpenFOAMEnvironmentPlugin())
    ctx = driver_context(plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.openfoam.environment"
    assert ctx.capabilities.dictionaries.entries() == ()
    assert plugin.get_tutorial_catalog() == {"registered_tutorials": (), "spec_factories": {}}


def test_minimal_plugin_proves_non_cardiac_solver_contract() -> None:
    plugin = validate_plugin(MinimalOpenFOAMPlugin())
    ctx = driver_context(plugin, source="test")

    assert ctx.identity.to_json()["providers"][-1]["id"] == "org.driverfoam.test-minimal"
    assert ctx.capabilities.dictionaries.entries() == ()
    assert plugin.get_capabilities() == {}
