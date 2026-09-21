"""The cardiac plugin's half of the plugin-API-version contract.

Moved from packages/omnidriver/tests/core/test_plugin_api_version.py: each
of these was one half of a test that checked cardiac AND generic together
(test_builtin_plugins_are_v2, test_both_builtin_plugins_satisfy_the_full_
protocol). The generic half of each stayed in core, using
openfoam_environment_context() / OpenFOAMEnvironmentPlugin(), which already passed
without cardiacfoam installed.
"""

from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def test_cardiacfoam_plugin_is_v2() -> None:
    """Half of what was test_builtin_plugins_are_v2; the generic half stayed
    in core as test_generic_builtin_plugin_is_v2."""
    assert CardiacFoamPlugin().plugin_api_version == "2"


def test_cardiacfoam_plugin_satisfies_the_full_protocol() -> None:
    """Half of what was test_both_builtin_plugins_satisfy_the_full_protocol:
    cardiac AND generic must each exercise every required capability -- this
    test previously caught the generic plugin declaring v2 while
    implementing only 8 of 12, riding the adapter's degrade-to-empty
    fallback. The generic half stayed in core as
    test_generic_builtin_plugin_satisfies_the_full_protocol, preserving that
    same intent there.

    NOT `isinstance(plugin, SolverPlugin)` (Task 9): `SolverPlugin` lists
    `get_environment_commands`/`is_installed_environment_command` as Protocol
    members, so that structural check demands them of this ONE class -- but
    this plugin now composes those from the environment provider rather than
    embedding them, exactly what Task 9 set out to do. `validate_plugin` is
    the real "implements every v2-required member" gate: it derives the
    required set from the capability seams' `:status:` tiers, where both
    those hooks are optional-neutral, and raises `TypeError` on a genuine
    gap -- which is what this test still needs to catch.
    """
    from omnidriver.core.plugin_interface import validate_plugin

    validate_plugin(CardiacFoamPlugin())  # must not raise


def test_cardiacfoam_declares_its_phases_in_order() -> None:
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:phases")
    assert context.capabilities.dictionaries.phases() == (
        "anatomy", "physics", "stimulus", "solver",
    )
