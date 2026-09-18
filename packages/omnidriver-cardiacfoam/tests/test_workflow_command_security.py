"""Cardiac-specific command-boundary assertions.

Moved from packages/omnidriver/tests/core/test_workflow_command_security.py:
these two cases assert that commands owned by the cardiac plugin itself
(``cardiacFoam``, its own solver binary, and ``bathBidomainInterfaceMetrics``,
an unmanifested post-solve utility it authorizes directly) are accepted by
the workflow-command allowlist. That is cardiac plugin knowledge, not a
property of core's generic command-boundary mechanism, so it belongs here
rather than in core's test tree.
"""
from __future__ import annotations

import unittest

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(CardiacFoamPlugin(), source="test:workflow_command_security")
from omnidriver.core.runtime.workflow import validate_workflow_commands


class TestCardiacWorkflowCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.context = _CTX

    def test_known_openfoam_command_is_allowed(self) -> None:
        dag = {"steps": [{"id": "s", "command": "cardiacFoam"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_bath_bidomain_interface_metrics_is_allowed(self) -> None:
        # bath_tet's canonical reported metrics come from this utility (a
        # post-hoc pass over the reconstructed mesh, since the live verifier
        # can't do heart/bath mesh-subsetting during a parallel-decomposed
        # solve) run as its own workflow step after solve -- authorized by the
        # cardiac plugin (it ships no utility.manifest.toml), not by core.
        dag = {"steps": [{"id": "s", "command": "bathBidomainInterfaceMetrics"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())


if __name__ == "__main__":
    unittest.main()
