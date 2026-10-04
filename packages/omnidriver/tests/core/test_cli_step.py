"""``step`` over the conformance toy: run one step, edit the staged case with
``--apply`` (the ``document:key`` patches a study takes), and ``recover``."""
from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from omnidriver import cli
from omnidriver.cli import main
from cli_refusal import refusal
from omnidriver.core import case_transaction
from plugins.toy import (
    EXPLAINING_PLUGIN, FAILS_UNTIL_SEVEN_CELLS_PLUGIN, RULE_CHECKING_PLUGIN, SOLVER_LOG_EXPLAINING_PLUGIN,
    STALE_SOLVER_LOG_PLUGIN, TWO_STEP_PLUGIN, write_toy_native_case,
)

PLUGIN = "plugins.toy:ToyStack"


def _cli(*argv: str) -> tuple[int, dict]:
    out = StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, json.loads(out.getvalue())


class _Case:
    """A planned toy record: its staged case and the run document ``plan`` wrote."""

    def __init__(self, tmp_path: Path, plugin: str = PLUGIN) -> None:
        self.plugin = plugin
        write_toy_native_case(tmp_path / "native")
        code, plan = _cli(
            "plan", "--strict", "--plugin", plugin, "--entry", "toyTutorial",
            "--cases-root", str(tmp_path / "native"), "--scratch-dir", str(tmp_path / "scratch"),
        )
        assert code == 0 and plan["status"] == "ok", plan
        self.root = tmp_path / "scratch" / "records" / "toyTutorial"
        self.run_document = self.root / "run_document.json"
        self.mesh = self.root / "constant" / "mesh.json"
        self.patches = tmp_path / "patches.json"

    def step(self, *extra: str, step: str = "solve") -> tuple[int, dict]:
        return _cli(
            "step", "--plugin", self.plugin, "--run-document", str(self.run_document), "--step", step, *extra,
        )

    def apply(self, study: dict, **kwargs) -> tuple[int, dict]:
        self.patches.write_text(json.dumps(study))
        return self.step("--apply", str(self.patches), **kwargs)

    def cells(self) -> str:
        return json.loads(self.mesh.read_text())["cells"]


@pytest.fixture
def case(tmp_path) -> _Case:
    return _Case(tmp_path)


def test_a_step_runs_and_writes_its_state_and_logs(case):
    code, payload = case.step()

    assert code == 0 and payload["status"] == "ok"
    assert (case.root / "solved.marker").is_file()
    assert Path(payload["stdout_log"]).is_file()
    assert json.loads((case.root / "workflow_state.json").read_text()) == payload["workflow_state"]
    assert "applied_patches" not in payload


def test_apply_edits_the_staged_case_then_reruns_the_step(case):
    code, payload = case.apply({"constant/mesh.json:cells": 7})

    assert code == 0 and payload["status"] == "ok"
    assert case.cells() == "7"
    assert json.loads(case.mesh.read_text())["label"] == "toy"
    assert [(p["document"], p["key_path"], p["value"], p["status"]) for p in payload["applied_patches"]] == [
        ("constant/mesh.json", ["cells"], 7, "changed"),
    ]
    (record,) = (json.loads(line) for line in (case.root / "remediation_history.jsonl").read_text().splitlines())
    assert record["resulting_status"] == "ok"
    assert record["applied_patches"] == payload["applied_patches"]


def test_a_patch_that_changes_nothing_does_not_rerun_a_failed_step_and_exits_non_zero(tmp_path):
    case = _Case(tmp_path, FAILS_UNTIL_SEVEN_CELLS_PLUGIN)
    assert case.step()[0] == 1
    logs = sorted(p.name for p in (case.root / "workflow_logs").iterdir())

    code, payload = case.apply({"constant/mesh.json:cells": 1})

    assert code == 1 and payload["status"] == "unchanged"
    assert "not rerun" in payload["message"]
    assert [p["status"] for p in payload["applied_patches"]] == ["unchanged"]
    assert sorted(p.name for p in (case.root / "workflow_logs").iterdir()) == logs
    assert not (case.root / "remediation_history.jsonl").exists()


def test_a_patch_that_changes_nothing_still_runs_a_step_that_never_ran(case):
    code, payload = case.apply({"constant/mesh.json:cells": 1})

    assert code == 0 and payload["status"] == "ok"
    assert [p["status"] for p in payload["applied_patches"]] == ["unchanged"]
    assert not (case.root / ".omnidriver" / "case-transactions").exists()
    assert (case.root / "solved.marker").is_file()


def test_a_step_reports_the_artifacts_it_left_on_disk(case):
    code, payload = case.step()

    assert code == 0
    assert payload["artifact_reconciliation"]["artifacts"][0]["status"] == "matched"


def test_a_key_the_record_does_not_accept_is_refused_and_nothing_runs(case):
    before = case.mesh.read_text()
    code, payload = case.apply({"constant/mesh.json:cells": 7, "constant/mesh.json:nope": 1})

    assert code == 1
    assert "candidate rejected" in payload["error"] and "constant/mesh.json:nope" in payload["error"]
    assert case.mesh.read_text() == before
    assert not (case.root / "solved.marker").exists()


def test_an_axis_name_is_refused_because_it_changes_the_plan(case):
    code, payload = case.apply({"number_cells": 7})

    assert code == 1
    assert "plan again" in payload["error"]
    assert case.cells() == "1"


def test_apply_needs_a_staged_case_so_it_refuses_entry(tmp_path, capsys):
    assert "--run-document" in refusal(
        capsys, ["step", "--plugin", PLUGIN, "--entry", "toyTutorial", "--step", "solve", "--apply", "p.json"],
    )


def test_an_interrupted_edit_blocks_the_case_until_recover_restores_it(case, monkeypatch):
    original = case_transaction._write_one

    def write_then_die(target, rendered):
        original(target, rendered)
        raise KeyboardInterrupt

    monkeypatch.setattr(case_transaction, "_write_one", write_then_die)
    with pytest.raises(KeyboardInterrupt):
        case.apply({"constant/mesh.json:cells": 7})
    monkeypatch.undo()
    assert case.cells() == "7"

    code, payload = case.step()
    assert code == 1 and "recover" in payload["error"]

    code, payload = _cli("recover", "--case-root", str(case.root))
    assert code == 0 and payload["transaction_id"]
    assert case.cells() == "1"

    code, payload = case.step()
    assert code == 0 and payload["status"] == "ok"


def test_recover_with_nothing_interrupted_says_so(case):
    code, payload = _cli("recover", "--case-root", str(case.root))

    assert code == 0 and payload["transaction_id"] is None


def test_an_edit_that_breaks_a_rule_is_rolled_back_and_the_case_still_takes_a_valid_edit(tmp_path):
    case = _Case(tmp_path, FAILS_UNTIL_SEVEN_CELLS_PLUGIN)
    code, payload = case.step()
    assert code == 1 and payload["status"] == "failed"

    code, payload = case.apply({"constant/mesh.json:cells": 12})
    assert code == 1 and "12 cells exceed 10" in payload["error"] and "as it was" in payload["error"]
    assert case.cells() == "1"
    assert "applied_patches" not in payload
    assert not (case.root / ".omnidriver" / "case-transaction.json").exists()

    code, payload = case.apply({"constant/mesh.json:cells": 7})
    assert code == 0 and payload["status"] == "ok", payload
    assert (case.root / "solved.marker").is_file()
    assert [s["attempt"] for s in payload["workflow_state"]["steps"]] == [2]


def test_an_edit_of_a_completed_step_is_refused_before_the_case_is_touched(case):
    code, _ = case.step()
    assert code == 0

    code, payload = case.apply({"constant/mesh.json:cells": 7})

    assert code == 1 and "'completed'" in payload["error"]
    assert case.cells() == "1"
    assert not (case.root / "remediation_history.jsonl").exists()


def test_an_edit_of_a_step_whose_dependencies_are_incomplete_is_refused_before_the_case_is_touched(tmp_path):
    case = _Case(tmp_path, TWO_STEP_PLUGIN)

    code, payload = case.apply({"constant/mesh.json:cells": 7})

    assert code == 1 and "incomplete dependencies" in payload["error"]
    assert case.cells() == "1"


def test_a_failed_rerun_after_an_edit_still_takes_the_next_edit(tmp_path):
    case = _Case(tmp_path, FAILS_UNTIL_SEVEN_CELLS_PLUGIN)
    assert case.step()[0] == 1

    code, payload = case.apply({"constant/mesh.json:cells": 9})
    assert code == 1
    assert case.cells() == "9"

    code, payload = case.apply({"constant/mesh.json:cells": 7})
    assert code == 0 and payload["status"] == "ok", payload


def test_a_failed_step_carries_what_the_stack_reads_in_its_log(tmp_path):
    case = _Case(tmp_path, EXPLAINING_PLUGIN)
    code, payload = case.step()
    assert code == 1 and payload["status"] == "failed"
    (explained,) = payload["failure_context"]["diagnostics"]
    assert (explained["code"], explained["field"], explained["message"]) == (
        "widget_missing", "widget", "widget is missing from toyTutorial",
    )
    (state,) = (s for s in payload["workflow_state"]["steps"] if s["step_id"] == "solve")
    assert state["diagnostics"] == [explained]


def test_a_step_that_exits_zero_is_failed_by_what_the_solver_wrote_in_its_own_log(tmp_path):
    case = _Case(tmp_path, SOLVER_LOG_EXPLAINING_PLUGIN)
    code, payload = case.step()
    assert code == 1 and payload["status"] == "failed"
    (explained,) = payload["failure_context"]["diagnostics"]
    assert (explained["code"], explained["field"]) == ("widget_missing", "widget")


def test_a_solver_log_the_step_did_not_write_explains_nothing(tmp_path):
    case = _Case(tmp_path, STALE_SOLVER_LOG_PLUGIN)
    (case.root / "solver.log").write_text("cannot find widget\n")
    os.utime(case.root / "solver.log", (1, 1))
    code, payload = case.step()
    assert code == 0 and payload["status"] == "ok", payload


def test_a_run_document_names_the_stack_it_was_planned_for(case, monkeypatch):
    """With no --plugin or --repo the command the plan recorded says which installed plugin and repository."""
    document = json.loads(case.run_document.read_text())
    document["launch"]["command"] = ["python", "-m", "omnidriver", "run", "--plugin", "toy-stack", "--repo", "/repo"]
    case.run_document.write_text(json.dumps(document))
    seen = {}

    def select(parser, args):
        seen["plugin"], seen["repo"] = args.plugin, args.repo
        raise SystemExit(0)

    monkeypatch.setattr(cli, "_select_stack", select)
    with pytest.raises(SystemExit):
        main(["step", "--run-document", str(case.run_document), "--step", "solve"])
    assert seen == {"plugin": "toy-stack", "repo": "/repo"}

    document["launch"]["command"] = ["python", "-m", "omnidriver", "run", "--plugin", "some.module:Class"]
    case.run_document.write_text(json.dumps(document))
    with pytest.raises(SystemExit):
        main(["step", "--run-document", str(case.run_document), "--step", "solve"])
    assert seen == {"plugin": None, "repo": None}
