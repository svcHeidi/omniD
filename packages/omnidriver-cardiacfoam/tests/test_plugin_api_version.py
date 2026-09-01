"""The cardiac plugin's half of the plugin-API-version contract.

Moved from packages/omnidriver/tests/core/test_plugin_api_version.py: each
of these was one half of a test that checked cardiac AND generic together
(test_builtin_plugins_are_v2, test_both_builtin_plugins_satisfy_the_full_
protocol). The generic half of each stayed in core, using
generic_openfoam_context() / GenericOpenFOAMPlugin(), which already passed
without cardiacfoam installed.
"""

from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


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
    same intent there."""
    from omnidriver.core.plugin_interface import SolverPlugin

    assert isinstance(CardiacFoamPlugin(), SolverPlugin)
