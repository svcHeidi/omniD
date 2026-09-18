"""Generic command authorization is plugin-owned, not baked into Core."""

from __future__ import annotations

from omnidriver.core.runtime.workflow import (
    CORE_NEUTRAL_COMMANDS,
    validate_workflow_commands,
)
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_core_neutral_commands_contain_no_solver_names() -> None:
    assert "cardiacFoam" not in CORE_NEUTRAL_COMMANDS
    assert "bathBidomainInterfaceMetrics" not in CORE_NEUTRAL_COMMANDS
    # OpenFOAM tooling is declared by its adapter, not Core.
    assert "blockMesh" not in CORE_NEUTRAL_COMMANDS
    assert "decomposePar" not in CORE_NEUTRAL_COMMANDS
    assert "mpirun" in CORE_NEUTRAL_COMMANDS


def test_minimal_plugin_does_not_authorize_a_solver_command() -> None:
    context = driver_context(MinimalTestPlugin(), source="test:commands")
    codes = {
        d.code for d in validate_workflow_commands(
            _dag("solver-command"), driver_context=context
        )
    }
    assert "unknown_workflow_command" in codes


def test_no_context_accepts_only_core_commands() -> None:
    codes = {d.code for d in validate_workflow_commands(_dag("solver-command"))}
    assert "unknown_workflow_command" in codes


def test_minimal_plugin_does_not_authorize_undeclared_commands() -> None:
    context = driver_context(MinimalTestPlugin(), source="test:commands")

    codes = {
        diagnostic.code
        for diagnostic in validate_workflow_commands(
            _dag("another-command"), driver_context=context,
        )
    }

    assert "unknown_workflow_command" in codes


def test_case_scripts_remain_core_owned() -> None:
    context = driver_context(MinimalTestPlugin(entrypoint="run-test-case"), source="test:commands")
    assert validate_workflow_commands(_dag("run-test-case"), driver_context=context) == ()
    assert validate_workflow_commands(_dag("./run-test-case"), driver_context=context) == ()


def test_generic_plugin_authorizes_neither_kind_of_command() -> None:
    auth = driver_context(MinimalTestPlugin(), source="test:commands").capabilities.command_authorization
    assert auth.solver_commands() == frozenset()
    assert auth.auxiliary_commands() == frozenset()
