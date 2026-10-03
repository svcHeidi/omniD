"""Cardiac-plugin-owned halves of command authorization: its own solver, its
unmanifested utilities and its bundled utility manifests.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context, load_plugin_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.core.runtime.workflow import validate_workflow_commands

# Supplied, not discovered: with a second adapter installed there is no default.
_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:command_authorization",
)


def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_cardiac_plugin_authorizes_its_unmanifested_utility() -> None:
    """gradientReconstructionOrder has no utility.manifest.toml; manufacturedEikonalECG's tet route needs it."""
    context = _CTX
    errors = [
        d for d in validate_workflow_commands(
            _dag("gradientReconstructionOrder"), driver_context=context
        )
        if d.level == "error"
    ]
    assert errors == []


def test_cardiac_plugin_authorizes_its_own_solver() -> None:
    context = _CTX
    errors = [
        d for d in validate_workflow_commands(_dag("cardiacFoam"), driver_context=context)
        if d.level == "error"
    ]
    assert errors == []


def test_cardiac_utilities_come_from_the_plugin() -> None:
    context = _CTX
    manifests = context.stack.call("get_utility_manifests")
    assert "listCellModelsVariables" in manifests
    generic = load_plugin_context("openfoam-environment")
    assert generic.stack.call("get_utility_manifests") == {}


def test_solver_and_auxiliary_commands_are_distinct() -> None:
    """Only solver_commands() may be credited with a run's artifacts (normalize_workflow_dag)."""
    solver = _CTX.stack.call("get_solver_commands")
    auxiliary = _CTX.stack.call("get_auxiliary_commands")
    assert solver == frozenset({"cardiacFoam"})
    assert auxiliary == frozenset({"gradientReconstructionOrder"})
    assert not (solver & auxiliary)


def test_utility_manifests_are_not_a_shared_mutable_dict() -> None:
    """The cache hands every caller the same object, so none may corrupt it for the others."""
    from omnidriver.cardiacfoam.command_authorization import (
        utility_manifests,
    )

    cached = utility_manifests()
    with pytest.raises(TypeError):
        cached["injected"] = object()  # type: ignore[index]

    # The most specific provider, last in the ordered stack, is cardiacFoam.
    plugin = _CTX.providers[-1]
    handed_out = plugin.get_utility_manifests()
    handed_out["injected"] = object()
    assert "injected" not in plugin.get_utility_manifests()


def test_plugin_utility_root_is_its_own_bundled_data() -> None:
    """Core has no knowledge of where any plugin's utility manifests live."""
    from omnidriver.cardiacfoam.command_authorization import utility_roots

    (root,) = utility_roots()
    assert root.is_dir()
    assert root.name == "utilities"
    assert (root / "listCellModelsVariables" / "utility.manifest.toml").is_file()
