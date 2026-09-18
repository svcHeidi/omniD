"""A case's entrypoint script comes from the plugin's declared role.

Core is entitled to the entrypoint concept; the spelling belongs to the
plugin. See future/ENVIRONMENT_CONTRACT.md.

Scope: discovery and runnability only. Which bare command names may resolve to a
case-local executable is a trust decision and stays in CASE_SCRIPT_COMMANDS.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime import registry

import plugins.minimal_plugin as minimal_plugin


def test_plugin_finds_its_declared_entrypoint(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "run-test-case").write_text("#!/bin/sh\n")
    context = driver_context(
        minimal_plugin.MinimalTestPlugin(entrypoint="run-test-case"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is True
    assert registry._case_is_runnable(case, driver_context=context) is True


def test_a_plugin_declaring_another_entrypoint_finds_it(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "run.sh").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalTestPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is True
    assert registry._case_is_runnable(case, driver_context=context) is True


def test_that_plugin_does_not_claim_an_undeclared_case_script(tmp_path) -> None:
    """The point of declaring: a plugin whose entrypoint is run.sh must not
    claim a folder just because it happens to contain another script."""
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "different-run-case").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalTestPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is False


def test_no_declaration_does_not_invent_an_entrypoint(tmp_path) -> None:
    """A plugin must declare its environment's case-script spelling."""
    context = driver_context(
        minimal_plugin.MinimalTestPlugin(entrypoint=None),
        source="test:no-entrypoint",
    )
    assert registry._entrypoint_relpaths(context) == ()
