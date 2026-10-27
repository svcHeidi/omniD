"""``--case DIR -- <options>``: the entrypoint's own options, as the case folder's ``args`` axis, from the CLI or a sweep."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from omnidriver.cli import main
from cli_refusal import refusal
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.record_execution import _parallel_workflow_dag, _workflow_dag_for_record
from omnidriver.core.tutorial_records import TutorialRecordError, case_folder_record

from plugins.toy import E2EFolderPlugin

_DECLARED = "plugins.toy:E2EFolderPlugin"


def _case(root: Path) -> Path:
    case = root / "myCase"
    (case / "constant").mkdir(parents=True)
    (case / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"}))
    script = case / "run-test-case"
    script.write_text('#!/bin/sh\necho "$@" > options.marker\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return case


def _plan(capsys, tmp_path: Path, *argv: str) -> tuple[int, dict]:
    code = main(["plan", "--strict", "--plugin", _DECLARED, "--scratch-dir", str(tmp_path / "scratch"), *argv])
    return code, json.loads(capsys.readouterr().out)


def test_the_case_folder_record_declares_one_axis_for_the_entrypoint_options(tmp_path):
    record, _ = case_folder_record(_case(tmp_path), driver_context=driver_context(E2EFolderPlugin(), source="test"))
    (axis,) = record.axes
    assert (axis.name, axis.value_kind) == ("args", "word_list")
    assert axis.resolve(["-N", "10"], tmp_path).command_arguments == {"run": ("-N", "10")}


def test_options_after_a_bare_double_dash_are_the_run_steps_arguments_in_the_run_document(tmp_path, capsys):
    case = _case(tmp_path / "cases")
    code, payload = _plan(capsys, tmp_path, "--case", str(case), "--", "-N", "10", "parallel")

    assert code == 0, payload
    (step,) = payload["run_document"]["workflowDag"]["steps"]
    assert (step["command"], step["args"]) == ("run-test-case", ["-N", "10", "parallel"])
    notes = [d for d in payload["run_document"]["validation"]["diagnostics"] if d["code"] == "entrypoint_options_unplanned"]
    assert [note["detail"] for note in notes] == [{"options": ["-N", "10", "parallel"]}]


def test_a_plan_without_options_runs_the_entrypoint_bare_and_notes_nothing(tmp_path, capsys):
    code, payload = _plan(capsys, tmp_path, "--case", str(_case(tmp_path / "cases")))

    assert code == 0, payload
    (step,) = payload["run_document"]["workflowDag"]["steps"]
    assert step["args"] == []
    assert not [d for d in payload["run_document"]["validation"]["diagnostics"] if d["code"] == "entrypoint_options_unplanned"]


def test_run_passes_the_options_to_the_entrypoint(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    case = _case(tmp_path / "cases")

    code = main([
        "run", "--strict", "--plugin", _DECLARED, "--case", str(case), "--scratch-dir", str(tmp_path / "scratch"),
        "--", "-mesh", "hex", "-N", "10",
    ])

    assert code == 0, capsys.readouterr().out
    assert (tmp_path / "scratch" / "records" / "myCase" / "options.marker").read_text() == "-mesh hex -N 10\n"
    assert not (case / "options.marker").exists()


def test_an_option_that_is_not_a_word_is_refused_by_the_axis(tmp_path, capsys):
    code, payload = _plan(capsys, tmp_path, "--case", str(_case(tmp_path / "cases")), "--", "two words")
    assert code == 1 and "axis 'args'" in payload["error"], payload


@pytest.mark.parametrize("argv", [
    ["plan", "--strict", "--entry", "toyTutorial", "--cases-root", "x", "--", "-N", "10"],
    ["sweep-plan", "--spec", "sweep.json", "--", "-N", "10"],
    ["catalog", "--case", "dir", "--", "-N", "10"],
])
def test_options_are_refused_where_no_case_folder_runs(argv, capsys):
    assert "only valid with --case" in refusal(capsys, [*argv, "--plugin", _DECLARED])


def _sweep(tmp_path: Path, base: dict, independent: dict) -> Path:
    spec = tmp_path / "sweep.json"
    spec.write_text(json.dumps({"base": base, "sweep": {"mode": "zip", "independent": independent}}))
    return spec


def test_a_sweep_names_a_case_folder_and_varies_its_options_and_its_keys(tmp_path, capsys):
    case = _case(tmp_path / "cases")
    spec = _sweep(
        tmp_path, {"case": str(case)},
        {"args": [["-N", "10"], ["-N", "20"]], "constant/mesh.json:cells": [10, 20], "caseId": ["N10", "N20"]},
    )
    before = sorted(p.as_posix() for p in case.rglob("*"))

    code = main(["sweep-plan", "--plugin", _DECLARED, "--spec", str(spec), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    for planned, n in zip(payload["cases"], ("10", "20")):
        (step,) = planned["plan"]["workflow_dag"]["steps"]
        assert step["args"] == ["-N", n]
        staged = tmp_path / "out" / "cases" / f"N{n}"
        assert json.loads((staged / "constant" / "mesh.json").read_text())["cells"] == n
    assert sorted(p.as_posix() for p in case.rglob("*")) == before


def test_options_in_base_and_in_the_sweep_that_differ_are_refused_per_case(tmp_path, capsys):
    spec = _sweep(tmp_path, {"case": str(_case(tmp_path / "cases")), "args": ["-dim", "1"]}, {"args": [["-N", "10"]]})

    code = main(["sweep-plan", "--plugin", _DECLARED, "--spec", str(spec), "--output-dir", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1, payload
    (case,) = payload["cases"]
    assert case["status"] == "failed" and "conflicting command arguments" in case["error"]


def test_a_sweep_names_a_case_folder_or_a_record_never_both(tmp_path, capsys):
    case = _case(tmp_path / "cases")
    spec = _sweep(tmp_path, {"case": str(case), "entry": "toyTutorial"}, {"args": [["-N", "10"]]})
    assert "a sweep is over one of them" in refusal(
        capsys, ["sweep-plan", "--plugin", _DECLARED, "--spec", str(spec), "--output-dir", str(tmp_path / "out")],
    )


def test_a_relative_case_folder_needs_a_repository(tmp_path, capsys):
    spec = _sweep(tmp_path, {"case": "cases/myCase"}, {"args": [["-N", "10"]]})
    assert "pass --repo" in refusal(
        capsys, ["sweep-plan", "--plugin", _DECLARED, "--spec", str(spec), "--output-dir", str(tmp_path / "out")],
    )


class _EntrypointParallelToy(E2EFolderPlugin):
    """Its parallel form keeps an entrypoint step as it is, as a layer whose entrypoint decomposes itself does."""

    handed: list = []

    def get_parallel_steps(self, step, *, request, read_value, allocation, launcher):
        self.handed.append((step["command"], request))
        return [dict(step)]


def test_a_parallel_request_hands_the_entrypoint_step_to_the_stacks_parallel_form(tmp_path):
    context = driver_context(_EntrypointParallelToy(), source="test")
    record, _ = case_folder_record(_case(tmp_path), driver_context=context)
    serial = _workflow_dag_for_record(record, workflow_step_ids=("run",), command_arguments={"run": ("parallel",)})

    parallel = _parallel_workflow_dag(
        record, serial, request=4, driver_context=context, read_value=lambda *_: None, allocation=None,
    )

    assert _EntrypointParallelToy.handed == [("run-test-case", 4)]
    assert [(s["command"], s["args"]) for s in parallel["steps"]] == [("run-test-case", ["parallel"])]


def test_a_stack_with_no_parallel_form_still_refuses_a_parallel_case_folder(tmp_path):
    context = driver_context(E2EFolderPlugin(), source="test")
    record, _ = case_folder_record(_case(tmp_path), driver_context=context)
    serial = _workflow_dag_for_record(record, workflow_step_ids=("run",), command_arguments={})
    with pytest.raises(TutorialRecordError, match="get_parallel_steps"):
        _parallel_workflow_dag(record, serial, request=2, driver_context=context, read_value=lambda *_: None, allocation=None)
