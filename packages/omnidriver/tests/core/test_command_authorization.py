"""Generic command authorization is plugin-owned, not baked into Core."""

from __future__ import annotations

from omnidriver.core.runtime.workflow import (
    CORE_NEUTRAL_COMMANDS,
    validate_workflow_commands,
)
from omnidriver.core.plugin_interface import driver_context
from plugins.toy import ToyProvider


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
    context = driver_context(ToyProvider(), source="test:commands")
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
    context = driver_context(ToyProvider(), source="test:commands")

    codes = {
        diagnostic.code
        for diagnostic in validate_workflow_commands(
            _dag("another-command"), driver_context=context,
        )
    }

    assert "unknown_workflow_command" in codes


def test_case_scripts_remain_core_owned() -> None:
    context = driver_context(ToyProvider(entrypoint="run-test-case"), source="test:commands")
    assert validate_workflow_commands(_dag("run-test-case"), driver_context=context) == ()
    assert validate_workflow_commands(_dag("./run-test-case"), driver_context=context) == ()


def test_generic_plugin_authorizes_neither_kind_of_command() -> None:
    stack = driver_context(ToyProvider(), source="test:commands").stack
    assert stack.call("get_solver_commands") == frozenset()
    assert stack.call("get_auxiliary_commands") == frozenset()


def test_mpi_wrapped_payload_is_authorized() -> None:
    """An mpirun wrapper must not launder an unauthorized binary."""
    from omnidriver.core.runtime import workflow

    context = driver_context(ToyProvider(), source="test:commands")
    dag = {"steps": [{
        "id": "solve",
        "command": "mpirun",
        "args": ["-np", "4", "definitelyNotAuthorized", "-parallel"],
    }]}
    problems = workflow.validate_workflow_commands(dag, driver_context=context)
    assert any(
        getattr(p, "code", None) == "unauthorized_mpi_payload"
        for p in problems
    ), f"expected an unauthorized_mpi_payload diagnostic, got {problems}"


def test_mpi_wrapped_authorized_solver_is_accepted() -> None:
    from omnidriver.core.runtime import workflow

    context = driver_context(
        ToyProvider(solver_commands={"authorized-solver"}),
        source="test:commands",
    )
    solver = next(iter(context.stack.call("get_solver_commands")))
    dag = {"steps": [{
        "id": "solve",
        "command": "mpirun",
        "args": ["-np", "4", solver, "-parallel"],
    }]}
    problems = workflow.validate_workflow_commands(dag, driver_context=context)
    assert not any(
        getattr(p, "code", None) == "unauthorized_mpi_payload"
        for p in problems
    )
