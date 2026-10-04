"""Owned edit/replanning/dispatch contracts for the CLI execution edge."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver import cli
from omnidriver.core.runtime.attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.case_transaction import _write_journal


def _dag(command: str = "ignored") -> dict:
    return {
        "steps": [{
            "id": "run",
            "command": command,
            "args": [],
            "cwd": ".",
            "depends_on": [],
            "produces": [],
            "consumes": [],
        }],
    }


def _args(apply_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        action="step",
        fresh=False,
        step="run",
        apply=str(apply_path),
        tail_lines=20,
        max_total_attempts=None,
    )


def test_apply_replan_and_dispatch_share_case_and_output_ownership(
    monkeypatch, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    apply_path = tmp_path / "patches.json"
    apply_path.write_text(json.dumps({"constant/mesh.json:cells": 2}))
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    events: list[str] = []

    def assert_owned() -> None:
        assert case_lease_is_held(case_root)
        assert attempt_lease_is_held(output_dir)

    def apply_study(study) -> tuple:
        assert_owned()
        events.append("apply")
        return ({"document": "constant/mesh.json", "status": "changed", **study},)

    def replan() -> cli._ReplannedExecution:
        assert_owned()
        events.append("replan")
        return cli._ReplannedExecution(dag, state, ())

    def runner(*args, **kwargs) -> WorkflowStepRunResult:
        del args
        assert kwargs["leases_held"] is True
        assert_owned()
        events.append("dispatch")
        step = replace(state.steps[0], status="completed", attempt=1, exit_code=0)
        completed = replace(
            state, status="completed", current_step_id=None,
            completed_steps=("run",), steps=(step,),
        )
        return WorkflowStepRunResult(completed, "run", 0, "stdout.log", "stderr.log")

    monkeypatch.setattr(cli, "run_workflow_step", runner)
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        apply_study=apply_study,
        replan_after_mutation=replan,
    )

    assert cli._dispatch_context(_args(apply_path), context) == 0
    assert events == ["apply", "replan", "dispatch"]
    audit = json.loads((output_dir / "remediation_history.jsonl").read_text())
    assert audit["resulting_status"] == "ok"
    assert audit["applied_patches"][0]["constant/mesh.json:cells"] == 2


def test_changed_replanned_workflow_is_refused_before_dispatch(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    apply_path = tmp_path / "patches.json"
    apply_path.write_text('{"constant/mesh.json:cells": 2}')
    dag = _dag()
    state = initial_workflow_state(dag)
    changed_dag = _dag("different-command")
    changed_state = initial_workflow_state(changed_dag)
    assert state is not None and changed_state is not None

    def unexpected_runner(*args, **kwargs):
        del args, kwargs
        raise AssertionError("dispatch must not run after plan identity changes")

    monkeypatch.setattr(cli, "run_workflow_step", unexpected_runner)
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        apply_study=lambda study: ({"status": "changed"},),
        replan_after_mutation=lambda: cli._ReplannedExecution(
            changed_dag, changed_state, (),
        ),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "changed the workflow plan" in payload["error"]
    audit = json.loads((output_dir / "remediation_history.jsonl").read_text())
    assert audit["resulting_status"] == "replan_error"


def test_a_plan_with_no_record_case_refuses_apply(capsys, tmp_path: Path) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    apply_path = tmp_path / "patches.json"
    apply_path.write_text('{"constant/mesh.json:cells": 2}')
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case", workflow_dag=dag, planned_state=state, case_root=case_root,
        output_dir=tmp_path / "output", expected_artifacts=(),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1
    assert "no tutorial record whose case can be edited" in json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize("body", ["[1, 2]", '"text"', "not json"])
def test_apply_takes_a_json_object_of_patches(capsys, tmp_path: Path, body: str) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    apply_path = tmp_path / "patches.json"
    apply_path.write_text(body)
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case", workflow_dag=dag, planned_state=state, case_root=case_root,
        output_dir=tmp_path / "output", expected_artifacts=(),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1
    assert "--apply rejected" in json.loads(capsys.readouterr().out)["error"]


def test_cli_reports_case_ownership_conflict_without_a_traceback(
    capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=tmp_path / "output",
        expected_artifacts=(),
    )

    with acquire_case_lease(case_root):
        assert cli._dispatch_context(_args(tmp_path / "unused.json"), context) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "case root is already owned" in payload["error"]


def test_fresh_refuses_live_output_owner_before_deleting_contents(
    capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "runs" / "case" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "workflow_state.json").write_text("{}")
    sentinel = output_dir / "must-survive"
    sentinel.write_text("owned")
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        source_path="run_document.json",
    )
    args = _args(tmp_path / "unused.json")
    args.fresh = True

    with acquire_attempt_lease(output_dir):
        assert cli._dispatch_context(args, context) == 1

    assert sentinel.read_text() == "owned"
    payload = json.loads(capsys.readouterr().out)
    assert "output directory is already owned" in payload["error"]


def test_an_interrupted_case_transaction_blocks_a_step(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    _write_journal(case_root, {
        "transaction_id": "interrupted", "plan_id": "p", "plan_digest": "d",
        "state": "applying", "before_images": [], "created_dirs": [],
    })
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
    )
    args = _args(tmp_path / "unused.json")
    args.apply = None
    monkeypatch.setattr(
        cli,
        "run_workflow_step",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("interrupted case must not dispatch")
        ),
    )

    assert cli._dispatch_context(args, context) == 1

    payload = json.loads(capsys.readouterr().out)
    assert "was interrupted" in payload["error"]


def test_an_interrupted_case_transaction_blocks_a_full_run(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    _write_journal(case_root, {
        "transaction_id": "interrupted", "plan_id": "p", "plan_digest": "d",
        "state": "applying", "before_images": [], "created_dirs": [],
    })
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
    )
    args = _args(tmp_path / "unused.json")
    args.action = "run"
    args.apply = None
    monkeypatch.setattr(
        cli,
        "run_workflow",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("interrupted case must not dispatch a full run")
        ),
    )

    assert cli._dispatch_context(args, context) == 1

    payload = json.loads(capsys.readouterr().out)
    assert "was interrupted" in payload["error"]
