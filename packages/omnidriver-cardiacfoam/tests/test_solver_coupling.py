"""Contract tests for solver_coupling.SOLVER_COMPATIBILITY_RULES.

Locks the table's shape so an edit cannot silently drop a field that
introspection and the describe-tutorial payload depend on."""
from __future__ import annotations

import unittest

from omnidriver.cardiacfoam.solver_coupling import SOLVER_COMPATIBILITY_RULES


class TestSolverCompatibilityRules(unittest.TestCase):
    _REQUIRED_KEYS: frozenset[str] = frozenset({
        "myocardium_solver",
        "purkinje_solver",
        "required_coupler",
        "valid",
    })

    def test_every_rule_has_required_keys(self) -> None:
        for rule in SOLVER_COMPATIBILITY_RULES:
            missing = self._REQUIRED_KEYS - set(rule)
            self.assertEqual(
                missing, set(),
                f"rule {rule!r} is missing required keys: {sorted(missing)}",
            )

    def test_invalid_rules_carry_a_reason(self) -> None:
        for rule in SOLVER_COMPATIBILITY_RULES:
            if not rule["valid"]:
                self.assertIn(
                    "reason", rule,
                    f"invalid rule {rule!r} must explain why it is invalid",
                )
                self.assertTrue(rule["reason"], "reason must not be empty")

    def test_valid_rules_have_a_required_coupler(self) -> None:
        for rule in SOLVER_COMPATIBILITY_RULES:
            if rule["valid"]:
                self.assertIsNotNone(
                    rule["required_coupler"],
                    f"valid rule {rule!r} must declare its required_coupler",
                )


if __name__ == "__main__":
    unittest.main()
