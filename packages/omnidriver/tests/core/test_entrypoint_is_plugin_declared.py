"""A case's entrypoint script comes from the plugin's declared role.

'Allrun' is OpenFOAM's spelling of a concept every simulation environment has.
Core is entitled to the concept; the spelling belongs to the plugin, declared as
role 'openfoam.entrypoint'. See future/ENVIRONMENT_CONTRACT.md.

Scope: discovery and runnability only. Which bare command names may resolve to a
case-local executable is a trust decision and stays in CASE_SCRIPT_COMMANDS.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context
from omnidriver.core.runtime import registry

import plugins.minimal_plugin as minimal_plugin


def test_generic_plugin_still_finds_an_allrun_case(tmp_path) -> None:
    """Behaviour preservation: the shipped profiles declare Allrun, so every
    answer this file changes must be identical to the hardcoded one."""
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")
    assert registry._is_case_directory(case, generic_openfoam_context()) is True
    assert registry._case_is_runnable(case, driver_context=generic_openfoam_context()) is True


def test_a_plugin_declaring_another_entrypoint_finds_it(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "run.sh").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is True
    assert registry._case_is_runnable(case, driver_context=context) is True


def test_that_plugin_does_not_claim_an_allrun_case(tmp_path) -> None:
    """The point of declaring: a plugin whose entrypoint is run.sh must not
    claim a folder just because it happens to contain an OpenFOAM Allrun."""
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is False


def test_no_declaration_falls_back_to_allrun(tmp_path) -> None:
    """Documented default, not a hidden one: a plugin declaring no entrypoint
    keeps the historical Allrun answer rather than becoming un-runnable."""
    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint=None),
        source="test:no-entrypoint",
    )
    assert registry._entrypoint_relpaths(context) == ("Allrun",)
