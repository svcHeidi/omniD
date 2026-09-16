"""Test plugin that declares the one authored input used by resume tests."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from plugins.declared_case_plugin import DeclaredCasePlugin


class ResumeTestPlugin(DeclaredCasePlugin):
    def get_profile(self) -> PluginProfile:
        rule = CaseFileRule(
            path="system/settings", kind="test_configuration",
            role="x-test.configuration", required="always",
        )
        return PluginProfile(
            path=Path(__file__), plugin_id=self.plugin_id,
            api_version=self.plugin_api_version, case_files=(rule,), cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                "case_profile": {"dictionaries": [{
                    "path": rule.path, "kind": rule.kind, "role": rule.role,
                    "required": rule.required,
                }]},
            },
        )
