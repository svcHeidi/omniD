"""Cardiac-plugin-owned halves of command authorization.

Moved from packages/omnidriver/tests/core/test_command_authorization.py:
these assertions name the cardiac plugin's own solver, its unmanifested
utilities, and its bundled utility-manifest package data -- cardiac
vocabulary and cardiac package layout, not core's generic
command-authorization mechanism. The generic-plugin half of that file (which
already passed without cardiacfoam installed) stayed in core as the model
for the split.
"""

from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import (
    default_driver_context,
    generic_openfoam_context,
)
from omnidriver.core.runtime.workflow import validate_workflow_commands


def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_cardiac_plugin_authorizes_its_unmanifested_utility() -> None:
    """gradientReconstructionOrder has no utility.manifest.toml, so it cannot
    come through utility_manifests(); the plugin must authorize it directly or
    manufactured_eikonal_ecg.py's gradient_reconstruction=True workflow stops
    validating."""
    context = default_driver_context()
    errors = [
        d for d in validate_workflow_commands(
            _dag("gradientReconstructionOrder"), driver_context=context
        )
        if d.level == "error"
    ]
    assert errors == []


def test_cardiac_plugin_authorizes_its_own_solver() -> None:
    context = default_driver_context()
    errors = [
        d for d in validate_workflow_commands(_dag("cardiacFoam"), driver_context=context)
        if d.level == "error"
    ]
    assert errors == []


def test_cardiac_utilities_come_from_the_plugin() -> None:
    context = default_driver_context()
    manifests = context.capabilities.command_authorization.utility_manifests()
    assert "listCellModelsVariables" in manifests
    generic = generic_openfoam_context()
    assert generic.capabilities.command_authorization.utility_manifests() == {}


def test_solver_and_auxiliary_commands_are_distinct() -> None:
    """Both are authorized, but only solver_commands() may be credited with a
    run's artifacts (see normalize_workflow_dag's producer heuristic)."""
    auth = default_driver_context().capabilities.command_authorization
    assert auth.solver_commands() == frozenset({"cardiacFoam"})
    assert auth.auxiliary_commands() == frozenset({"gradientReconstructionOrder"})
    assert not (auth.solver_commands() & auth.auxiliary_commands())


def test_utility_manifests_are_not_a_shared_mutable_dict() -> None:
    """The cache hands the same object to every caller, so no consumer may be
    able to corrupt the authorization input of all the others."""
    from omnidriver.cardiacfoam.command_authorization import (
        utility_manifests,
    )

    cached = utility_manifests()
    with pytest.raises(TypeError):
        cached["injected"] = object()  # type: ignore[index]

    plugin = default_driver_context().plugin
    handed_out = plugin.get_utility_manifests()
    handed_out["injected"] = object()
    assert "injected" not in plugin.get_utility_manifests()


def test_plugin_utility_root_is_its_own_bundled_data() -> None:
    """The plugin owns its utilities root as package data, not a path core
    hands it -- core has no knowledge of where any plugin's utility
    manifests live (see future/UTILITY_CATALOG_STANDALONE_GAP.md)."""
    from omnidriver.cardiacfoam.command_authorization import utility_roots

    (root,) = utility_roots()
    assert root.is_dir()
    assert root.name == "utilities"
    assert (root / "listCellModelsVariables" / "utility.manifest.toml").is_file()
