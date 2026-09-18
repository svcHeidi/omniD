"""Run dispatch preserves context and reports incomplete budget-limited work."""
import argparse
import json
import sys
from functools import partial

import pytest

from omnidriver import cli
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.workflow_orchestrator import run_workflow
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from plugins.minimal_plugin import MinimalTestPlugin


@pytest.mark.parametrize("budget", [0, 1])
def test_run_dispatch_context_and_incomplete_budget(tmp_path, monkeypatch, capsys, budget):
    dag = {"steps": [
        {"id": name, "command": sys.executable, "args": ["-c", "pass"],
         "cwd": ".", "depends_on": [] if name == "first" else ["first"]}
        for name in ("first", "second")
    ]}
    context = driver_context(MinimalTestPlugin(), source="test:dispatch")
    received = []

    def runner(*args, driver_context, **kwargs):
        received.append(driver_context)
        # The explicit neutral adapter checks dispatch identity without
        # restoring an implicit environment default.
        return run_workflow_step(*args, **kwargs)

    monkeypatch.setattr(cli, "run_workflow", partial(run_workflow, runner=runner))
    monkeypatch.setattr(cli, "run_postprocess_phase", lambda **kwargs: pytest.fail("incomplete run postprocessed"))
    execution = cli._ExecutionContext(
        entry_label="local", workflow_dag=dag, planned_state=initial_workflow_state(dag),
        case_root=tmp_path, output_dir=tmp_path / "output", expected_artifacts=(),
        driver_context=context,
    )
    args = argparse.Namespace(action="run", fresh=False, tail_lines=10, max_total_attempts=budget)
    assert cli._dispatch_context(args, execution) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] != "ok"
    assert payload["workflow_state"]["status"] == "pending"
    assert "maximum total step attempts" in payload["error"]
    assert payload["postprocess"]["status"] == "skipped"
    assert len(received) == budget
    assert all(value is context for value in received)
