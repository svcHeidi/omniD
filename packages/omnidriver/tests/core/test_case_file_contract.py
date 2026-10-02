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
    assert contract.all_rules() == ()
    assert context.capabilities.case_runtime_conventions.conventions() == CORE_RUNTIME_RECORDS
    assert context.capabilities.case_provenance.input_roots(
        Path("case"), {}, conventions=CORE_RUNTIME_RECORDS,
    ) == ()


def test_a_declared_case_script_is_a_rule_of_the_contract() -> None:
    contract = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    ).capabilities.case_files
    assert [(rule.path, rule.required) for rule in contract.all_rules()] == [("run-test-case", "conditional")]
