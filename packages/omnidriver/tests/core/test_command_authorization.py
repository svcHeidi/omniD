"""Command authorization is plugin-owned, not baked into core."""

from __future__ import annotations

from omnidriver.openfoam.environment import openfoam_environment_context
from omnidriver.core.runtime.workflow import (
    CORE_NEUTRAL_COMMANDS,
    validate_workflow_commands,
)
from plugins.neutral_environment_plugin import NeutralEnvironmentPlugin
from omnidriver.core.plugin_interface import driver_context
def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_core_neutral_commands_contain_no_solver_names() -> None:
    assert "cardiacFoam" not in CORE_NEUTRAL_COMMANDS
    assert "bathBidomainInterfaceMetrics" not in CORE_NEUTRAL_COMMANDS
    # OpenFOAM tooling is declared by its adapter, not Core.
    assert "blockMesh" not in CORE_NEUTRAL_COMMANDS
    assert "decomposePar" not in CORE_NEUTRAL_COMMANDS
    assert "mpirun" in CORE_NEUTRAL_COMMANDS


def _without_installed_openfoam_apps(monkeypatch) -> None:
    """Isolate plugin authorization from the OpenFOAM runtime declaration.

    The OpenFOAM adapter deliberately accepts any executable installed under
    its app roots, so a user's compiled utility can run without a catalog
    entry. With OpenFOAM sourced, cardiacFoam may be such an executable -- so
    it is accepted by that declaration regardless of solver semantics.

    These two tests originally asserted outright rejection and passed only
    because OpenFOAM happened not to be sourced in the authoring environment:
    they encoded an environment accident as a security property. Suppressing
    the installed-app rule pins what they actually mean -- that the generic
    plugin does not authorize cardiacFoam *as a plugin command*.
    """
    monkeypatch.setattr(
        "omnidriver.openfoam.environment.is_installed_openfoam_application",
        lambda command: False,
    )


def test_generic_plugin_does_not_authorize_the_cardiac_solver(monkeypatch) -> None:
    _without_installed_openfoam_apps(monkeypatch)
    context = openfoam_environment_context()
    codes = {
        d.code for d in validate_workflow_commands(
            _dag("cardiacFoam"), driver_context=context
        )
    }
    assert "unknown_workflow_command" in codes


def test_no_context_accepts_only_core_commands(monkeypatch) -> None:
    _without_installed_openfoam_apps(monkeypatch)
    codes = {d.code for d in validate_workflow_commands(_dag("blockMesh"))}
    assert "unknown_workflow_command" in codes
    codes = {d.code for d in validate_workflow_commands(_dag("cardiacFoam"))}
    assert "unknown_workflow_command" in codes


def test_generic_openfoam_environment_authorizes_its_declared_commands() -> None:
    assert validate_workflow_commands(
        _dag("blockMesh"), driver_context=openfoam_environment_context(),
    ) == ()


def test_neutral_environment_does_not_authorize_openfoam_commands() -> None:
    context = driver_context(NeutralEnvironmentPlugin(), source="test:commands")

    codes = {
        diagnostic.code
        for diagnostic in validate_workflow_commands(
            _dag("blockMesh"), driver_context=context,
        )
    }

    assert "unknown_workflow_command" in codes


def test_an_installed_openfoam_app_is_authorized_whatever_the_plugin(monkeypatch) -> None:
    """The other half, pinned deliberately rather than left to the environment.

    This is documented behaviour, not a leak: an executable present under
    $FOAM_APPBIN / $FOAM_USER_APPBIN is accepted so a user's own compiled
    utility can run. Stating it here means the boundary is described by tests
    in both directions instead of only the one the environment happened to
    exercise.
    """
    monkeypatch.setattr(
        "omnidriver.openfoam.environment.is_installed_openfoam_application",
        lambda command: command == "someInstalledApp",
    )
    context = openfoam_environment_context()
    errors = [
        d for d in validate_workflow_commands(
            _dag("someInstalledApp"), driver_context=context
        )
        if d.level == "error"
    ]
    assert errors == []


def test_case_scripts_remain_core_owned() -> None:
    context = openfoam_environment_context()
    assert validate_workflow_commands(_dag("Allrun"), driver_context=context) == ()
    assert validate_workflow_commands(_dag("./Allrun"), driver_context=context) == ()


def test_generic_plugin_authorizes_neither_kind_of_command() -> None:
    auth = openfoam_environment_context().capabilities.command_authorization
    assert auth.solver_commands() == frozenset()
    assert auth.auxiliary_commands() == frozenset()
