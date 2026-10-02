"""Case-file declarations are consumed generically by Core."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS
from plugins.minimal_plugin import MinimalTestPlugin


def test_minimal_plugin_declares_no_case_files() -> None:
    context = driver_context(
        MinimalTestPlugin(), source="test:minimal-case-files",
    )
    contract = context.capabilities.case_files
    assert contract.required_files() == ()
    assert contract.conditional_files() == ()
    assert context.capabilities.case_runtime_conventions.conventions() == CORE_RUNTIME_RECORDS
    assert context.capabilities.case_provenance.input_roots(
        Path("case"), {}, conventions=CORE_RUNTIME_RECORDS,
    ) == ()


def test_conditional_files_are_separated_from_required() -> None:
    """Exercises `_CaseFileContractAdapter`'s always/conditional split -- core mechanics, not solver vocabulary."""
    contract = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    ).capabilities.case_files
    assert "run-test-case" in contract.conditional_files()
    assert "run-test-case" not in contract.required_files()
