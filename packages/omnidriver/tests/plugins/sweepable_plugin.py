"""Test plugin implementing both sweep hooks, importable by a child process.

It lives here, not inside a test module, because ``sweep_run`` executes each
case in a ``python -m omnidriver run`` subprocess that must rebuild the same
plugin from its ``--plugin module:Class`` selector.
"""

from __future__ import annotations

from plugins.declared_case_plugin import DeclaredCasePlugin


class SweepablePlugin(DeclaredCasePlugin):
    """A non-cardiac plugin implementing both sweep hooks.

    The base supplies only the declared entrypoint, output root, and no-op
    preflight that a sweep reaches before its own routing hooks run.
    """

    def route_sweep_case_values(self, *, base, resolved_axis_values, driver_context):
        return {**base, **resolved_axis_values}

    def materialize_sweep_case(self, *, case_dir, routed):
        # Write the declared case script so strict planning can resolve the
        # materialized folder, and make it runnable so a real case execution
        # completes. A materializer that only mkdir'd would make the operation
        # fail downstream for reasons unrelated to context threading.
        case_dir.mkdir(parents=True, exist_ok=True)
        script = case_dir / "run-test-case"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
