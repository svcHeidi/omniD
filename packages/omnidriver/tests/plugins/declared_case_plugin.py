"""Test plugin that declares one case-script convention for CLI tests."""

from __future__ import annotations

import os

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from plugins.minimal_plugin import MinimalTestPlugin


class DeclaredCasePlugin(MinimalTestPlugin):
    """Declares the script, output root, and no-op preflight a CLI run needs."""

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(
            output_collection_relpath="outputs",
            case_entrypoints=("run-test-case",),
            case_script_commands=("run-test-case",),
        )

    def get_capabilities(self):
        """An explicit empty manifest for CLI/plan serialization tests."""
        from omnidriver.core.capability_manifest import build_capability_manifest

        return build_capability_manifest(
            plugin_commands=frozenset(), utility_manifests={}, samplable_fields={},
        )

    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None,
    ) -> tuple:
        del workflow_dag, env, explicit_bashrc, driver_context
        return ()

    def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None) -> dict:
        del explicit_bashrc, driver_context
        return dict(os.environ)

    def get_configured_environment(self, env, driver_context) -> dict:
        del driver_context
        return dict(env)
