"""OpenFOAM adapter conformance to Core's plugin protocol."""

from __future__ import annotations

from omnidriver.core.plugin_interface import validate_plugin
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
    # NOT `isinstance(plugin, SolverPlugin)` (Task 9): `SolverPlugin` lists
    # `get_solver_commands`/`get_auxiliary_commands` as Protocol members
    # (solver-vocabulary hollow stubs this adapter no longer carries, per
    # Phase 0 Task 4's census), so that structural check would demand
    # solver-specific commands of the environment adapter -- exactly the
    # vocabulary core/ARCHITECTURE.md says an environment adapter must not
    # know. `validate_plugin` is the real "implements every v2-required
    # member" gate: it derives the required set from the capability seams'
    # `:status:` tiers, where both those hooks are optional-neutral.
    validate_plugin(OpenFOAMEnvironmentPlugin())  # must not raise
