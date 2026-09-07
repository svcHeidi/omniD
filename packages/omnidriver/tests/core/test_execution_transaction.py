"""Owned mutation/replanning/dispatch contracts for the CLI execution edge."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from omnidriver import cli
from omnidriver.core.runtime.attempt_lease import (
    acquire_attempt_lease,
    acquire_case_lease,
    attempt_lease_is_held,
    case_lease_is_held,
)
from omnidriver.core.runtime.workflow_runner import WorkflowStepRunResult
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.runtime.remediation_transaction import (
    begin_remediation_transaction,
    read_remediation_transaction,
)


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
    apply_path = tmp_path / "overrides.json"
    apply_path.write_text(json.dumps({
        "hypothesis": "the proposed value removes the observed instability",
        "overrides": [{"driver_path": "value", "value": "2"}],
    }))
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    events: list[str] = []

    def assert_owned() -> None:
        assert case_lease_is_held(case_root)
        assert attempt_lease_is_held(output_dir)

    def apply(overrides, **kwargs) -> None:
        del overrides, kwargs
        assert_owned()
        events.append("apply")

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
    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            override_scopes=SimpleNamespace(
                apply=apply,
                target_paths=lambda *args, **kwargs: (case_root / "config",),
            ),
        ),
    )
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        driver_context=driver_context,
        replan_after_mutation=replan,
    )

    assert cli._dispatch_context(_args(apply_path), context) == 0
    assert events == ["apply", "replan", "dispatch"]
    transaction = read_remediation_transaction(case_root)
    assert transaction["status"] == "accepted"
    assert transaction["hypothesis"] == (
        "the proposed value removes the observed instability"
    )
    assert transaction["execution_status"] == "ok"
    assert transaction["execution_attempt"] == 1


def test_changed_replanned_workflow_is_refused_before_dispatch(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    apply_path = tmp_path / "overrides.json"
    apply_path.write_text('[{"driver_path": "value", "value": "2"}]')
    dag = _dag()
    state = initial_workflow_state(dag)
    changed_dag = _dag("different-command")
    changed_state = initial_workflow_state(changed_dag)
    assert state is not None and changed_state is not None

    def unexpected_runner(*args, **kwargs):
        del args, kwargs
        raise AssertionError("dispatch must not run after plan identity changes")

    monkeypatch.setattr(cli, "run_workflow_step", unexpected_runner)
    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            override_scopes=SimpleNamespace(
                apply=lambda *args, **kwargs: None,
                target_paths=lambda *args, **kwargs: (case_root / "config",),
            ),
        ),
    )
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        driver_context=driver_context,
        replan_after_mutation=lambda: cli._ReplannedExecution(
            changed_dag, changed_state, (),
        ),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "changed the workflow plan" in payload["error"]


def test_unresolved_effective_value_is_audited_and_blocks_dispatch(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    apply_path = tmp_path / "overrides.json"
    overrides = [{"driver_path": "deltaT", "value": "0.0005"}]
    apply_path.write_text(json.dumps(overrides))
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None
    evidence = ({
        "driver_path": "deltaT",
        "requested_value": "0.0005",
        "status": "unresolved",
        "value": None,
        "parser": "foamDictionary",
        "runtime": "/runtime/openfoam",
        "message": "include dependency is unresolved",
    },)

    monkeypatch.setattr(
        cli,
        "run_workflow_step",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unresolved effective values must block dispatch")
        ),
    )
    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            override_scopes=SimpleNamespace(
                apply=lambda *args, **kwargs: evidence,
                target_paths=lambda *args, **kwargs: (case_root / "config",),
            ),
        ),
    )
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        driver_context=driver_context,
        replan_after_mutation=lambda: cli._ReplannedExecution(dag, state, ()),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "effective dictionary resolution failed" in payload["error"]
    audit = json.loads((output_dir / "remediation_history.jsonl").read_text())
    assert audit["resulting_status"] == "replan_error"
    assert audit["effective_dictionary_resolution"] == list(evidence)


def test_mutator_that_writes_then_raises_is_rejected_not_rolled_back(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    target = case_root / "config"
    target.write_text("baseline\n")
    output_dir = tmp_path / "output"
    apply_path = tmp_path / "overrides.json"
    apply_path.write_text('[{"driver_path": "value", "value": "2"}]')
    dag = _dag()
    state = initial_workflow_state(dag)
    assert state is not None

    def partial_apply(*args, **kwargs):
        del args, kwargs
        target.write_text("candidate\n")
        raise ValueError("resolver crashed after the write")

    driver_context = SimpleNamespace(
        capabilities=SimpleNamespace(
            override_scopes=SimpleNamespace(
                apply=partial_apply,
                target_paths=lambda *args, **kwargs: (target,),
            ),
        ),
    )
    context = cli._ExecutionContext(
        entry_label="case",
        workflow_dag=dag,
        planned_state=state,
        case_root=case_root,
        output_dir=output_dir,
        expected_artifacts=(),
        driver_context=driver_context,
        replan_after_mutation=lambda: cli._ReplannedExecution(dag, state, ()),
    )

    assert cli._dispatch_context(_args(apply_path), context) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["remediation_transaction"]["status"] == "rejected"
    transaction = read_remediation_transaction(case_root)
    assert transaction["status"] == "rejected"
    assert target.read_text() == "candidate\n"
    assert Path(transaction["candidate_archive"], "config").read_text() == "candidate\n"

    args = _args(apply_path)
    args.apply = None
    assert cli._dispatch_context(args, context) == 1
    assert "was rejected" in json.loads(capsys.readouterr().out)["error"]


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
    )
    args = _args(tmp_path / "unused.json")
    args.fresh = True

    with acquire_attempt_lease(output_dir):
        assert cli._dispatch_context(args, context) == 1

    assert sentinel.read_text() == "owned"
    payload = json.loads(capsys.readouterr().out)
    assert "output directory is already owned" in payload["error"]


def test_interrupted_configuration_blocks_cli_dispatch(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            begin_remediation_transaction(
                case_root, output_dir=output_dir, step_id="run",
                overrides=[{"driver_path": "value", "value": "2"}],
                hypothesis="candidate interrupted before validation",
                target_paths=(case_root / "config",),
            )
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
            AssertionError("interrupted candidate must not dispatch")
        ),
    )

    assert cli._dispatch_context(args, context) == 1

    payload = json.loads(capsys.readouterr().out)
    assert "was interrupted" in payload["error"]


def test_interrupted_configuration_blocks_full_run_dispatch(
    monkeypatch, capsys, tmp_path: Path,
) -> None:
    case_root = tmp_path / "case"
    case_root.mkdir()
    output_dir = tmp_path / "output"
    with acquire_case_lease(case_root):
        with acquire_attempt_lease(output_dir):
            begin_remediation_transaction(
                case_root, output_dir=output_dir, step_id="run",
                overrides=[{"driver_path": "value", "value": "2"}],
                hypothesis="candidate interrupted before validation",
                target_paths=(case_root / "config",),
            )
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
            AssertionError("interrupted candidate must not dispatch a full run")
        ),
    )

    assert cli._dispatch_context(args, context) == 1

    payload = json.loads(capsys.readouterr().out)
    assert "was interrupted" in payload["error"]
