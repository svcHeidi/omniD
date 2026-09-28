"""Commands the cardiac plugin owns (its solver and an unmanifested utility it
authorizes directly) pass the workflow-command allowlist.
"""
from __future__ import annotations

import unittest

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:workflow_command_security")
from omnidriver.core.runtime.workflow import validate_workflow_commands


class TestCardiacWorkflowCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.context = _CTX

    def test_known_openfoam_command_is_allowed(self) -> None:
        dag = {"steps": [{"id": "s", "command": "cardiacFoam"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_bath_bidomain_interface_metrics_is_allowed(self) -> None:
        # A post-solve pass over the reconstructed mesh: the live verifier cannot
        # subset heart/bath during a decomposed solve. It ships no utility.manifest.toml.
        dag = {"steps": [{"id": "s", "command": "bathBidomainInterfaceMetrics"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())


if __name__ == "__main__":
    unittest.main()
