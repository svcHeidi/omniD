"""Case-file declarations are consumed generically by Core."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


def test_minimal_plugin_declares_no_case_files() -> None:
    context = driver_context(
        MinimalTestPlugin(), source="test:minimal-case-files",
    )
    contract = context.capabilities.case_files
    assert contract.required_files() == ()
    assert contract.conditional_files() == ()
    assert context.capabilities.case_runtime_conventions.conventions() == CaseRuntimeConventions()
    assert context.capabilities.case_introspection.selected_start_time(
        Path("case"), {}, driver_context=context,
    ) is None


def test_conditional_files_are_separated_from_required() -> None:
    """Exercises `_CaseFileContractAdapter`'s always/conditional split -- core
    mechanics, not solver vocabulary. ``MinimalTestPlugin(entrypoint=...)``
    makes the test-only ``run-test-case`` entrypoint explicit; the mechanic
    under test is that conditional files are excluded from ``required_files``.
    """
    contract = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    ).capabilities.case_files
    assert "run-test-case" in contract.conditional_files()
    assert "run-test-case" not in contract.required_files()
