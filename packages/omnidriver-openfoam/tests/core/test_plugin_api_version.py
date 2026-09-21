"""OpenFOAM adapter conformance to Core's plugin protocol."""

from __future__ import annotations

from omnidriver.core.plugin_interface import SolverPlugin
from omnidriver.openfoam.environment import (
    OpenFOAMEnvironmentPlugin,
    openfoam_environment_context,
)


def test_openfoam_environment_plugin_is_v2() -> None:
    # StackIdentity has no singular api_version -- one per provider, on
    # StackIdentity.providers (a tuple of ProviderIdentity). A single-plugin
    # driver_context composes to a one-entry stack.
    context = openfoam_environment_context()
    assert context.identity.providers[0].api_version == "2"


def test_openfoam_environment_plugin_satisfies_the_full_protocol() -> None:
    assert isinstance(OpenFOAMEnvironmentPlugin(), SolverPlugin)
