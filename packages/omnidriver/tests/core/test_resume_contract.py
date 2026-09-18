"""Real local subprocess/checkpoint tests; no simulation installation needed."""
import copy
import json
import os
import sys
from dataclasses import replace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from omnidriver import cli
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.models import DataArtifact
from omnidriver.core.runtime.attempt_lease import acquire_attempt_lease, acquire_case_lease
from omnidriver.core.runtime.resume import validate_resume
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state, workflow_state_from_json
from plugins.resume_test_plugin import ResumeTestPlugin


def _completed(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system/settings").write_text("value 1;\n")
    dag = {"steps": [{"id": "solve", "command": sys.executable,
        "args": ["-c", "from pathlib import Path; Path('result.txt').write_text('done')"],
        "cwd": ".", "depends_on": []}]}
    context = driver_context(ResumeTestPlugin(), source="test:resume")
    output = tmp_path / "output"
    result = run_workflow_step(dag, initial_workflow_state(dag), "solve", case_root=tmp_path,
        log_dir=output / "logs", state_path=output / "workflow_state.json", env={}, driver_context=context)
    assert result.state.status == "completed"
    return dag, context, output, result.state


def test_unchanged_checkpoint_roundtrips_and_resumes(tmp_path):
    dag, context, output, state = _completed(tmp_path)
    saved = workflow_state_from_json(json.loads((output / "workflow_state.json").read_text()))
    assert saved == state
    validate_resume(saved, dag, case_root=tmp_path, driver_context=context, env={})


def test_internal_environment_transport_path_does_not_invalidate_resume(tmp_path):
    dag, context, output, _state = _completed(tmp_path)
    result = run_workflow_step(
        dag, initial_workflow_state(dag), "solve", case_root=tmp_path,
        log_dir=output / "transport-logs", state_path=output / "transport-state.json",
        env={"_DRIVER_ENV_FILE": "/private/tmp/first"}, driver_context=context,
    )
    saved = workflow_state_from_json(
        json.loads((output / "transport-state.json").read_text())
    )
    assert saved == result.state
    validate_resume(
        saved, dag, case_root=tmp_path, driver_context=context,
        env={"_DRIVER_ENV_FILE": "/private/tmp/second"},
    )


@pytest.mark.parametrize("change", ["input", "dag", "environment", "legacy", "inconsistent"])
def test_checkpoint_refuses_drift_or_unbound_state(tmp_path, change):
    dag, context, output, state = _completed(tmp_path)
    environment = {}
    if change == "input":
        (tmp_path / "system/settings").write_text("value 2;\n")
    elif change == "dag":
        dag = copy.deepcopy(dag)
        dag["steps"][0]["args"] = ["-c", "raise SystemExit(9)"]
    elif change == "environment":
        environment = {"NUMERICAL_MODE": "changed"}
    elif change == "legacy":
        state = replace(state, workflow_digest=None, resume_snapshot=None)
    else:
        state = replace(state, completed_steps=())
    with pytest.raises(ValueError):
        validate_resume(state, dag, case_root=tmp_path, driver_context=context, env=environment)


def test_cli_does_not_report_stale_completed_state_as_success(tmp_path, capsys):
    dag, context, output, state = _completed(tmp_path)
    (tmp_path / "system/settings").write_text("value 2;\n")
    assert cli._execute_run(entry_label="test", workflow_dag=dag,
        planned_state=initial_workflow_state(dag), case_root=tmp_path, output_dir=output,
        expected_artifacts=(), tail_lines=5, driver_context=context, execution_env={}) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "input evidence changed" in payload["error"]
    assert (output / "workflow_state.json").exists()


def test_cli_step_rejects_stale_inputs_too(tmp_path, capsys):
    dag, context, output, state = _completed(tmp_path)
    (tmp_path / "system/settings").write_text("value 2;\n")
    with acquire_case_lease(tmp_path):
        with acquire_attempt_lease(output):
            assert cli._execute_step(entry_label="test", step_id="solve", workflow_dag=dag,
                planned_state=initial_workflow_state(dag), case_root=tmp_path, output_dir=output,
                expected_artifacts=(), tail_lines=5, driver_context=context, execution_env={}) == 1
    assert "input evidence changed" in json.loads(capsys.readouterr().out)["error"]


def test_cli_step_reports_malformed_saved_state_as_json(tmp_path, capsys):
    dag = {"steps": [{
        "id": "solve", "command": sys.executable, "args": ["-c", "pass"],
        "cwd": ".", "depends_on": [],
    }]}
    state = initial_workflow_state(dag)
    output = tmp_path / "output"
    output.mkdir()
    (output / "workflow_state.json").write_text("{}")
    with acquire_case_lease(tmp_path):
        with acquire_attempt_lease(output):
            assert cli._execute_step(
                entry_label="test", step_id="solve", workflow_dag=dag,
                planned_state=state, case_root=tmp_path, output_dir=output,
                expected_artifacts=(), tail_lines=5,
            ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["workflow_state_path"] == str(output / "workflow_state.json")


def test_completed_checkpoint_requires_its_required_output_on_resume(tmp_path, capsys):
    """A completed state cannot turn a deleted required result into success."""
    dag, context, output, _ = _completed(tmp_path)
    expected = (DataArtifact(
        artifact_id="result", path_pattern="result.txt", format="text",
    ),)
    saved = workflow_state_from_json(json.loads((output / "workflow_state.json").read_text()))
    validate_resume(
        saved, dag, case_root=tmp_path, driver_context=context, env={},
        expected_artifacts=expected,
    )
    (tmp_path / "result.txt").unlink()
    with pytest.raises(ValueError, match="required outputs are missing.*result"):
        validate_resume(
            saved, dag, case_root=tmp_path, driver_context=context, env={},
            expected_artifacts=expected,
        )
    assert cli._execute_run(
        entry_label="test", workflow_dag=dag, planned_state=initial_workflow_state(dag),
        case_root=tmp_path, output_dir=output, expected_artifacts=expected,
        tail_lines=5, driver_context=context, execution_env={},
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "required outputs are missing" in payload["error"]


def test_run_document_embedded_completed_state_refuses_changed_inputs(tmp_path) -> None:
    """A RunDocument state is resumable evidence, not a success override.

    This uses the core-owned test plugin and a shell-only declared entrypoint so it
    proves the public CLI contract without any cardiacFOAM dependency.
    """
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    settings = case_root / "system" / "settings"
    settings.write_text("value 1;\n")
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(script, 0o755)

    workflow_dag = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [{
            "id": "run",
                "command": "run-test-case",
            "args": [],
            "cwd": ".",
            "depends_on": [],
            "produces": [],
            "consumes": [],
            "retry_policy": {"max_attempts": 1},
                "command_display": "run-test-case",
        }],
    }
    state = initial_workflow_state(workflow_dag)
    assert state is not None
    doc_path = tmp_path / "run.json"
    doc = {
        "version": "3",
        "id": "embedded-state",
        "name": "embedded-state",
        "createdAt": "",
        "lastModified": "",
        "status": "planned",
        "config": {},
        "resolvedEntry": None,
        "workflowDag": workflow_dag,
        "workflowState": state.to_json(),
        "launch": {"caseRoot": str(case_root), "outputDir": "output"},
        "expectedArtifacts": [],
        "validation": {},
        "terminalStatusValues": ["completed", "failed"],
    }
    doc_path.write_text(json.dumps(doc))

    first_out = StringIO()
    with redirect_stdout(first_out):
        first_code = cli.main([
            "run", "--plugin", "plugins.resume_test_plugin:ResumeTestPlugin",
            "--run-document", str(doc_path),
        ])
    first = json.loads(first_out.getvalue())
    assert first_code == 0, first

    # Simulate a RunDocument persisted after the first attempt rather than
    # the ordinary adjacent workflow_state.json checkpoint.
    saved_state_path = Path(first["workflow_state_path"])
    doc["workflowState"] = json.loads(saved_state_path.read_text())
    doc_path.write_text(json.dumps(doc))
    saved_state_path.unlink()
    settings.write_text("value 2;\n")

    resumed_out = StringIO()
    with redirect_stdout(resumed_out):
        resumed_code = cli.main([
            "run", "--plugin", "plugins.resume_test_plugin:ResumeTestPlugin",
            "--run-document", str(doc_path),
        ])
    resumed = json.loads(resumed_out.getvalue())
    assert resumed_code == 1, resumed
    assert resumed["status"] == "failed"
    assert "workflow_state_resume_rejected" in {
        diagnostic["code"] for diagnostic in resumed["diagnostics"]
    }
