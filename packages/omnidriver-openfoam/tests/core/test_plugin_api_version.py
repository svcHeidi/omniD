"""OpenFOAM adapter conformance to Core's plugin protocol."""

from __future__ import annotations

from omnidriver.core.plugin_interface import validate_plugin
from omnidriver.openfoam.environment import (
    OpenFOAMEnvironmentPlugin,
    openfoam_environment_context,
)


def test_openfoam_environment_plugin_is_v3() -> None:
    # StackIdentity carries no singular api_version, only one per provider
    # on StackIdentity.providers; a single-plugin context is a one-entry stack.
    context = openfoam_environment_context()
    assert context.identity.providers[0].api_version == "3"


def test_openfoam_environment_plugin_satisfies_the_contract() -> None:
    validate_plugin(OpenFOAMEnvironmentPlugin())  # must not raise
