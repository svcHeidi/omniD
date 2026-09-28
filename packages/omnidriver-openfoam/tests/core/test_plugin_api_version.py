"""OpenFOAM adapter conformance to Core's plugin protocol."""

from __future__ import annotations

from omnidriver.core.plugin_interface import validate_plugin
from omnidriver.openfoam.environment import (
    OpenFOAMEnvironmentPlugin,
    openfoam_environment_context,
)


def test_openfoam_environment_plugin_is_v2() -> None:
    # StackIdentity carries no singular api_version, only one per provider
    # on StackIdentity.providers; a single-plugin context is a one-entry stack.
    context = openfoam_environment_context()
    assert context.identity.providers[0].api_version == "2"


def test_openfoam_environment_plugin_satisfies_the_full_protocol() -> None:
    # Not `isinstance(plugin, SolverPlugin)`: that Protocol lists
    # `get_solver_commands`/`get_auxiliary_commands`, solver vocabulary an
    # environment adapter must not know (core/ARCHITECTURE.md). `validate_plugin`
    # derives the required set from the capability seams' `:status:` tiers,
    # where both those hooks are optional-neutral.
    validate_plugin(OpenFOAMEnvironmentPlugin())  # must not raise
