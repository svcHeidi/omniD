"""A record runs parallel through its solver layer."""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.record_execution import (
    SchedulerAllocation, _parallel_workflow_dag, _workflow_dag_for_record, commit_and_build_record_spec,
    preview_record_case, scheduler_allocation,
)
from omnidriver.core.tutorial_records import (
    PARALLEL_STUDY_NAME, AxisContract, AxisResult, TutorialRecord, TutorialRecordError, WorkflowStep,
)

from cli_refusal import refusal
from plugins.toy import PARALLEL_TOY_PLUGIN

TESTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
E2E_PLUGIN = "plugins.toy:ToyStack"

THREE_STEPS = TutorialRecord(
    name="threeSteps", native_case_relpath="threeSteps",
    workflow_steps=(
        WorkflowStep(step_id="mesh", command=("mkdir", "-p", "mesh")),
        WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                     consumes=("constant/mesh.json",), produces=("solved.marker",)),
        WorkflowStep(step_id="post", command=("cp", "solved.marker", "post.marker"), produces=("post.marker",)),
    ),
)


def _native_toy_case(tmp_path: Path, cells: str = "2") -> Path:
    native = tmp_path / "native" / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": cells}))
    return native.parent


def _serial(record=THREE_STEPS):
    return _workflow_dag_for_record(record, workflow_step_ids=record.step_ids(), command_arguments={})


def _reader(values):
    return lambda document, key_path: values[(document, tuple(key_path))]


def _toy_context():
    return load_plugin_context(PARALLEL_TOY_PLUGIN)


# -- the reserved name --------------------------------------------------------


def test_the_reserved_name_is_parallel():
    assert PARALLEL_STUDY_NAME == "parallel"


@pytest.mark.parametrize("field", ["axis", "selector"])
def test_a_record_may_not_claim_the_reserved_name(field):
    kwargs: dict = {}
    if field == "axis":
        kwargs["axes"] = (AxisContract(name="parallel", value_kind="scalar",
                                       resolve=lambda value, root: AxisResult()),)
    else:
        kwargs.update(variant_selector="parallel", default_variant="a", workflow_variants={"a": ("solve",)})
    with pytest.raises(TutorialRecordError, match="'parallel' is reserved"):
        TutorialRecord(name="r", native_case_relpath="r",
                       workflow_steps=(WorkflowStep(step_id="solve", command=("s",)),), **kwargs)


# -- the rewrite ----------------------------------------------------------------


def test_only_the_declared_solve_step_is_rewritten_and_the_chain_is_rewired():
    dag = _parallel_workflow_dag(
        THREE_STEPS, _serial(), request=True, driver_context=_toy_context(),
        read_value=_reader({("constant/mesh.json", ("cells",)): "4"}), allocation=None,
    )
    steps = {step["id"]: step for step in dag["steps"]}
    assert [step["id"] for step in dag["steps"]] == ["mesh", "solve.split", "solve", "solve.join", "post"]
    # the solve step keeps its id, its declared outputs and inputs
    assert steps["solve"]["args"] == ["solved.marker", "ranks.4"]
    assert steps["solve"]["produces"] == ["record.solve.0"]
    assert steps["solve"]["consumes"] == ["constant/mesh.json"]
    # the form's first step follows the solve's own predecessor; the next step follows its last
    assert steps["solve.split"]["depends_on"] == ["mesh"]
    assert steps["post"]["depends_on"] == ["solve.join"]
    # a step the stack does not declare as a solve step is untouched
    assert steps["mesh"]["args"] == ["-p", "mesh"]


def test_a_stack_without_a_parallel_form_is_refused_by_name():
    with pytest.raises(TutorialRecordError) as excinfo:
        _parallel_workflow_dag(
            THREE_STEPS, _serial(), request=True, driver_context=load_plugin_context(E2E_PLUGIN),
            read_value=_reader({}), allocation=None,
        )
    message = str(excinfo.value)
    assert "'threeSteps'" in message and "get_parallel_steps" in message and "serial" in message


def test_a_serial_only_record_is_refused_by_name_even_where_the_stack_has_a_parallel_form():
    record = dataclasses.replace(THREE_STEPS, serial_only=True)
    with pytest.raises(TutorialRecordError, match="serial only") as excinfo:
        _parallel_workflow_dag(record, _serial(record), request=True, driver_context=_toy_context(),
                               read_value=_reader({}), allocation=None)
    assert "'threeSteps'" in str(excinfo.value)


def test_a_record_with_no_declared_solve_step_is_refused_by_name():
    record = TutorialRecord(name="noSolve", native_case_relpath="noSolve",
                            workflow_steps=(WorkflowStep(step_id="post", command=("cp", "a", "b")),))
    with pytest.raises(TutorialRecordError, match="get_solve_step_commands") as excinfo:
        _parallel_workflow_dag(record, _serial(record), request=True, driver_context=_toy_context(),
                               read_value=_reader({}), allocation=None)
    assert "'touch'" in str(excinfo.value)


def test_the_solver_layers_refusal_names_the_record_and_the_step():
    with pytest.raises(TutorialRecordError) as excinfo:
        _parallel_workflow_dag(THREE_STEPS, _serial(), request=2, driver_context=_toy_context(),
                               read_value=_reader({("constant/mesh.json", ("cells",)): "4"}), allocation=None)
    message = str(excinfo.value)
    assert "'threeSteps'" in message and "'solve'" in message and "got request 2" in message


@pytest.mark.parametrize("form, fragment", [
    (lambda step: (), "returned no steps"),
    (lambda step: ({**step, "id": "renamed"},), "keep the solve step's id"),
    (lambda step: (step, dict(step)), "keep the solve step's id"),
    (lambda step: ({**step, "produces": []},), "keep its produces"),
    (lambda step: ({"id": "post", "command": "touch", "args": [], "depends_on": []}, step), "'post'"),
])
def test_a_form_that_breaks_the_rewrite_rules_is_refused(monkeypatch, form, fragment):
    context = _toy_context()
    monkeypatch.setattr(type(context.providers[-1]), "get_parallel_steps", lambda self, step, **_: form(step))
    with pytest.raises(TutorialRecordError, match=fragment):
        _parallel_workflow_dag(THREE_STEPS, _serial(), request=True, driver_context=context,
                               read_value=_reader({}), allocation=None)


# -- the scheduler's allocation: discovered, from one declared place ------------


def test_no_allocation_outside_a_scheduler():
    assert scheduler_allocation({}) is None


def test_the_allocation_is_read_from_slurm_ntasks():
    assert scheduler_allocation({"SLURM_NTASKS": "64"}) == SchedulerAllocation(variable="SLURM_NTASKS", ranks=64)


@pytest.mark.parametrize("bad", ["", "abc", "0", "-2", "2.5"])
def test_a_malformed_allocation_is_refused_by_name(bad):
    with pytest.raises(TutorialRecordError, match="SLURM_NTASKS"):
        scheduler_allocation({"SLURM_NTASKS": bad})


def test_the_solver_layer_sees_the_allocation_and_refuses_a_disagreement():
    with pytest.raises(TutorialRecordError, match="SLURM_NTASKS=8 disagrees"):
        _parallel_workflow_dag(
            THREE_STEPS, _serial(), request=True, driver_context=_toy_context(),
            read_value=_reader({("constant/mesh.json", ("cells",)): "4"}),
            allocation=SchedulerAllocation(variable="SLURM_NTASKS", ranks=8),
        )


# -- through the record pipeline: commit, preview, provenance -------------------


def test_a_committed_case_runs_serial_by_default(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    commit, spec = commit_and_build_record_spec(
        record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "staged",
        study_by_source={"base": {}}, driver_context=context,
    )
    assert [step["id"] for step in spec.metadata["workflow_dag"]["steps"]] == ["solve"]
    assert "parallel" not in spec.metadata
    assert commit.parallel_request is None


def test_parallel_false_is_serial(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    _commit, spec = commit_and_build_record_spec(
        record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"parallel": False}}, driver_context=context,
    )
    assert [step["id"] for step in spec.metadata["workflow_dag"]["steps"]] == ["solve"]
    assert "parallel" not in spec.metadata


def test_parallel_null_is_refused_by_name_never_read_as_serial(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    with pytest.raises(TutorialRecordError, match="'parallel' is null"):
        commit_and_build_record_spec(
            record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"parallel": None}}, driver_context=context,
        )


def test_the_count_is_read_from_the_committed_case(tmp_path, monkeypatch):
    """The study changes the toy's count and the form follows it: N comes from the case the run will see, never restated."""
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    cases_root = _native_toy_case(tmp_path, cells="2")
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    commit, spec = commit_and_build_record_spec(
        record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"parallel": True, "number_cells": 3}}, driver_context=context,
    )
    steps = {step["id"]: step for step in spec.metadata["workflow_dag"]["steps"]}
    assert steps["solve"]["args"] == ["solved.marker", "ranks.3"]
    assert spec.metadata["parallel"] == {"requested": True, "allocation": None}
    assert commit.parallel_request is True


def test_the_preview_shows_the_parallel_form_the_uncommitted_study_would_run(tmp_path, monkeypatch):
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    cases_root = _native_toy_case(tmp_path, cells="2")
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    preview = preview_record_case(
        record, cases_root=cases_root, driver_context=context,
        study_by_source={"base": {"parallel": True, "number_cells": 5}},
    )
    assert preview["parallel"] == {"requested": True, "allocation": None}
    assert preview["workflow_commands"] == {
        "solve.split": ["touch", "split.5"],
        "solve": ["touch", "solved.marker", "ranks.5"],
        "solve.join": ["touch", "joined.marker"],
    }


def test_an_allocation_in_the_environment_reaches_the_solver_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("SLURM_NTASKS", "2")
    cases_root = _native_toy_case(tmp_path, cells="2")
    context = _toy_context()
    record = context.stack.call("get_tutorial_records")["toyTutorial"]
    _commit, spec = commit_and_build_record_spec(
        record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "ok",
        study_by_source={"base": {"parallel": True}}, driver_context=context,
    )
    assert spec.metadata["parallel"] == {
        "requested": True, "allocation": {"variable": "SLURM_NTASKS", "ranks": 2},
    }
    with pytest.raises(TutorialRecordError, match="SLURM_NTASKS=2 disagrees with constant/mesh.json:cells=3"):
        commit_and_build_record_spec(
            record, case_id="c", cases_root=cases_root, staged_case_root=tmp_path / "bad",
            study_by_source={"base": {"parallel": True, "number_cells": 3}}, driver_context=context,
        )


# -- the request surface: a study value and the CLI, the same way ---------------


def _plan(tmp_path, capsys, *extra):
    cases_root = _native_toy_case(tmp_path)
    code = main(["plan", "--strict", "--plugin", PARALLEL_TOY_PLUGIN, "--entry", "toyTutorial",
                 "--cases-root", str(cases_root), "--scratch-dir", str(tmp_path / "scratch"), *extra])
    return code, json.loads(capsys.readouterr().out)


def _plan_with_study(tmp_path, study, cli_study=None):
    from omnidriver.core.strict_planning import strict_plan

    return strict_plan(
        "toyTutorial", overrides={"cases_root": str(_native_toy_case(tmp_path)), **study},
        cli_study=cli_study, scratch_root=tmp_path / "scratch",
        driver_context=load_plugin_context(PARALLEL_TOY_PLUGIN),
    ).to_json()


def test_the_cli_flag_and_the_study_value_plan_the_same_run(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    code_cli, from_cli = _plan(tmp_path / "cli", capsys, "--parallel")
    from_study = _plan_with_study(tmp_path / "study", {"parallel": True})
    assert code_cli == 0, from_cli

    def shape(payload):
        document = payload["run_document"]
        return ([(s["id"], s["command"], s["args"]) for s in document["workflowDag"]["steps"]],
                document["resolvedEntry"]["parallel"])

    assert shape(from_cli) == shape(from_study) == (
        [("solve.split", "touch", ["split.2"]), ("solve", "touch", ["solved.marker", "ranks.2"]),
         ("solve.join", "touch", ["joined.marker"])],
        {"requested": True, "allocation": None},
    )


def test_a_serial_run_document_says_nothing_of_parallel(tmp_path, capsys):
    code, payload = _plan(tmp_path, capsys)
    assert code == 0, payload
    assert "parallel" not in payload["run_document"]["resolvedEntry"]
    assert [s["id"] for s in payload["run_document"]["workflowDag"]["steps"]] == ["solve"]


def test_the_cli_and_a_study_that_disagree_are_refused_by_name(tmp_path):
    with pytest.raises(TutorialRecordError, match="'parallel' is set to different values") as caught:
        _plan_with_study(tmp_path, {"parallel": False}, cli_study={"parallel": True})
    assert "'cli'" in str(caught.value)


def test_the_cli_passes_a_value_to_the_solver_layer(tmp_path, capsys):
    code, payload = _plan(tmp_path, capsys, "--parallel", "3")
    assert code == 1
    assert "got request 3" in payload["error"]


def test_parallel_on_a_stack_without_a_form_is_refused_by_name_as_json(tmp_path, capsys):
    cases_root = _native_toy_case(tmp_path)
    code = main(["plan", "--strict", "--plugin", E2E_PLUGIN, "--entry", "toyTutorial",
                 "--cases-root", str(cases_root), "--scratch-dir", str(tmp_path / "scratch"), "--parallel"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert "get_parallel_steps" in payload["error"]


def test_describe_previews_the_cli_request(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    cases_root = _native_toy_case(tmp_path)
    code = main(["describe", "--plugin", PARALLEL_TOY_PLUGIN, "--entry", "toyTutorial",
                 "--cases-root", str(cases_root), "--parallel"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["record_preview"]["parallel"] == {"requested": True, "allocation": None}
    assert payload["record_preview"]["workflow_commands"]["solve"] == ["touch", "solved.marker", "ranks.2"]


@pytest.mark.parametrize("argv", [
    ["run", "--run-document", "doc.json", "--parallel"],
    ["env", "--plugin", "p", "--parallel"],
])
def test_the_flag_is_refused_where_nothing_is_planned(argv, capsys):
    assert "--parallel" in refusal(capsys, argv)


def test_a_sweep_compares_serial_against_parallel_and_both_run(tmp_path, monkeypatch):
    """The study value is sweepable, so one sweep holds a serial case and a parallel one; both run for real, through the child process, and each case's run document says which it was."""
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    cases_root = _native_toy_case(tmp_path)
    spec = {
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {"mode": "cross_product", "independent": {"parallel": [False, True]}},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(TESTS_ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env.pop("SLURM_NTASKS", None)
    result = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", PARALLEL_TOY_PLUGIN,
         "--spec", str(spec_path), "--output-dir", str(tmp_path / "out")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert [case["status"] for case in payload["cases"]] == ["completed", "completed"], payload
    shapes = []
    for case in payload["cases"]:
        document = json.loads((tmp_path / "out" / case["run_document_path"]).read_text())
        shapes.append(([s["id"] for s in document["workflowDag"]["steps"]],
                       document["resolvedEntry"].get("parallel")))
        case_root = Path(document["launch"]["caseRoot"])
        assert (case_root / "solved.marker").is_file()
    assert shapes == [
        (["solve"], None),
        (["solve.split", "solve", "solve.join"], {"requested": True, "allocation": None}),
    ]


def test_the_sweep_cli_flag_reaches_every_record_case(tmp_path, capsys):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps({
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {"mode": "cross_product", "independent": {"number_cells": [2]}},
    }))
    code = main(["sweep-plan", "--plugin", PARALLEL_TOY_PLUGIN, "--spec", str(spec_path),
                 "--output-dir", str(tmp_path / "out"), "--parallel"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    (case,) = payload["cases"]
    assert case["plan"]["run_document"]["resolvedEntry"]["parallel"] == {"requested": True, "allocation": None}


def test_run_strict_runs_the_parallel_form_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SLURM_NTASKS", raising=False)
    cases_root = _native_toy_case(tmp_path)
    code = main(["run", "--strict", "--plugin", PARALLEL_TOY_PLUGIN, "--entry", "toyTutorial",
                 "--cases-root", str(cases_root), "--scratch-dir", str(tmp_path / "scratch"), "--parallel"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["workflow_state"]["status"] == "completed"
    case_root = tmp_path / "scratch" / "records" / "toyTutorial"
    assert all((case_root / name).is_file() for name in ("split.2", "solved.marker", "ranks.2", "joined.marker"))
