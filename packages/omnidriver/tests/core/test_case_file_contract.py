"""Case-file declarations are consumed generically by Core."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, case_runtime_conventions
from plugins.toy import ToyProvider


def test_minimal_plugin_declares_no_case_files() -> None:
    context = driver_context(
        ToyProvider(), source="test:minimal-case-files",
    )
    assert context.stack.call("get_profile").case_files == ()
    assert case_runtime_conventions(context) == CORE_RUNTIME_RECORDS
    assert context.stack.call("get_input_roots", Path("case"), {}, conventions=CORE_RUNTIME_RECORDS) == ()


def test_a_declared_case_script_is_a_rule_of_the_contract() -> None:
    profile = driver_context(
        ToyProvider(entrypoint="run-test-case"), source="test"
    ).stack.call("get_profile")
    assert [(rule.path, rule.required) for rule in profile.case_files] == [("run-test-case", "conditional")]
