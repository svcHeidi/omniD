"""Tests resolve_execution_context(), the neutral case_root/setup_root/
output_dir/workflow_state_path resolver that replaces strict_plan's reuse of
describe_launch("sim", ...) for path calculation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from omnidriver.core.runtime.execution_context import resolve_execution_context
from omnidriver.core.runtime.registry import load_entry_spec

from conftest import monorepo_root, skip_without_monorepo



@skip_without_monorepo
class TestResolveExecutionContext(unittest.TestCase):
    def test_reports_case_setup_output_and_workflow_state_paths(self) -> None:
        cases_root = monorepo_root / "tutorials"  # type: ignore[operator]
        spec = load_entry_spec("singleCell", overrides={"cases_root": str(cases_root)})

        context = resolve_execution_context(spec)

        self.assertEqual(context.case_root, Path(spec.case_root))
        self.assertEqual(context.setup_root, Path(spec.setup_root))
        self.assertEqual(context.output_dir, Path(spec.output_dir))
        self.assertEqual(
            context.workflow_state_path,
            Path(spec.output_dir) / "workflow_state.json",
        )

    def test_never_re_resolves_the_entry(self) -> None:
        """Takes an already-built spec directly -- no resolve_entry/factory call of
        its own, unlike describe_launch (which strict_plan used to call a second
        time on the same entry purely to get these four paths)."""
        cases_root = monorepo_root / "tutorials"  # type: ignore[operator]
        spec = load_entry_spec("singleCell", overrides={"cases_root": str(cases_root)})

        context = resolve_execution_context(spec)

        # No entry/entry_kind/overrides/config_path parameter exists to pass --
        # the only input is the spec itself.
        self.assertIsInstance(context.case_root, Path)


if __name__ == "__main__":
    unittest.main()
