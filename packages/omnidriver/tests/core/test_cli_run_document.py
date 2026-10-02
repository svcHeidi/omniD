"""CLI integration tests for the --run-document execution path."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
from conftest import skip_without_repo, skip_without_single_adapter
pytestmark = [skip_without_repo, skip_without_single_adapter]

from omnidriver.cli import main

# Vendored copy of the cardiacFoam monorepo's singleCell tutorial
# dictionaries (see fixtures/single_cell_tutorial/README.md), shipped
# alongside this test file so it runs without a real cardiacFoam checkout
# instead of always skipping in CI.
SINGLE_CELL_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "single_cell_tutorial"


def _write_case(root: Path, *, allrun: str, steps: list[dict]) -> Path:
    case_root = root / "runDocCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "system").mkdir()
    (case_root / "constant" / "electroProperties").write_text(
        (SINGLE_CELL_ROOT / "constant" / "electroProperties").read_text()
    )
    (case_root / "constant" / "physicsProperties").write_text(
        (SINGLE_CELL_ROOT / "constant" / "physicsProperties").read_text()
    )
    for name in ("controlDict", "fvSchemes", "fvSolution"):
        (case_root / "system" / name).write_text("\n")
    allrun_path = case_root / "Allrun"
    allrun_path.write_text(allrun)
    os.chmod(allrun_path, 0o755)
    return case_root


def _plan_to_file(cases_root: Path, doc_path: Path) -> dict:
    """Run `plan --strict` and write its run_document to doc_path."""
    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "plan", "--strict", "--entry", "runDocCase",
            "--cases-root", str(cases_root),
        ])
    report = json.loads(out.getvalue())
    assert code == 0, report
    run_document = report["run_document"]
    assert run_document is not None
    doc_path.write_text(json.dumps(run_document))
    return run_document


def test_plan_then_run_document_round_trip_executes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
        _write_case(
            cases_root,
            allrun="#!/bin/sh\nmkdir -p postProcessing 0.001\ntouch postProcessing/runDocCase_1.txt 0.001/Vm 0.001/AV_Ta\nprintf 'ran\\n'\n",
            steps=[{"id": "run", "command": "Allrun", "depends_on": []}],
        )
        doc_path = cases_root / "run.json"
        _plan_to_file(cases_root, doc_path)

        out = StringIO()
        with redirect_stdout(out):
            code = main(["run", "--run-document", str(doc_path)])

        payload = json.loads(out.getvalue())
        assert code == 0, payload
        assert payload["status"] == "ok"
        assert payload["workflow_state"]["status"] == "completed"
        assert Path(payload["workflow_state_path"]).exists()
        assert payload["steps"]
        assert payload["steps"][0]["status"] == "ok"

        case_record_path = Path(payload["case_record_path"])
        assert case_record_path.exists()
        case_record = json.loads(case_record_path.read_text())
        run_document = json.loads(doc_path.read_text())
        # setup_root flows from the RunDocument's own launch.setupRoot into
        # the standalone case record -- an agent can discover this case's
        # postprocess scripts the same way it already can for a sweep case.
        # This fixture's case has no setup/ directory on disk, so check
        # round-trip fidelity against the RunDocument rather than existence.
        assert case_record["setup_root"] == run_document["launch"]["setupRoot"]


def test_step_via_run_document_executes_named_step() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
        _write_case(
            cases_root,
            allrun="#!/bin/sh\nmkdir -p postProcessing 0.001\ntouch postProcessing/runDocCase_1.txt 0.001/Vm 0.001/AV_Ta\nprintf 'ran\\n'\n",
            steps=[{"id": "run", "command": "Allrun", "depends_on": []}],
        )
        doc_path = cases_root / "run.json"
        _plan_to_file(cases_root, doc_path)

        out = StringIO()
        with redirect_stdout(out):
            code = main(["step", "--run-document", str(doc_path), "--step", "run"])

        payload = json.loads(out.getvalue())
        assert code == 0, payload
        assert payload["status"] == "ok"
        assert payload["workflow_state"]["steps"][0]["status"] == "completed"


def test_run_document_with_bad_dag_surfaces_diagnostics() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text(json.dumps({
            "version": "3",
            "id": "d",
            "name": "bad",
            "status": "planned",
            "config": {"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
            "configurationSource": "document",
            "launch": {},
            "workflowDag": None,
        }))

        out = StringIO()
        with redirect_stdout(out):
            code = main(["run", "--run-document", str(doc_path)])

        payload = json.loads(out.getvalue())
        assert code == 1
        assert payload["status"] == "failed"
        codes = {d["code"] for d in payload["diagnostics"]}
        assert "missing_workflow_dag" in codes
        assert "missing_case_root" in codes


def test_run_document_rejects_unknown_command() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text(json.dumps({
            "version": "3",
            "id": "d",
            "name": "danger",
            "status": "planned",
            "config": {"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
            "configurationSource": "document",
            "launch": {"caseRoot": temp_dir, "outputDir": temp_dir},
            "workflowDag": {
                "schema_version": "1",
                "step_status_values": [
                    "pending", "running", "completed", "failed", "skipped",
                ],
                "steps": [
                    {"id": "s", "command": "rm", "args": ["-rf", "/"], "cwd": ".",
                     "depends_on": [], "produces": [], "consumes": [],
                     "retry_policy": {}, "command_display": "rm -rf /"},
                ],
            },
        }))

        out = StringIO()
        with redirect_stdout(out):
            code = main(["run", "--run-document", str(doc_path)])

        payload = json.loads(out.getvalue())
        assert code == 1
        codes = {d["code"] for d in payload["diagnostics"]}
        assert "unknown_workflow_command" in codes


def test_run_document_and_entry_are_mutually_exclusive() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text("{}")
        try:
            main(["run", "--run-document", str(doc_path), "--entry", "singleCell"])
        except SystemExit as exc:
            assert exc.code == 2  # argparse parser.error
            return
        raise AssertionError("expected SystemExit from mutually-exclusive args")


def test_run_document_only_valid_for_run_and_step() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text("{}")
        try:
            main(["describe", "--run-document", str(doc_path)])
        except SystemExit as exc:
            assert exc.code == 2
            return
        raise AssertionError("expected SystemExit for --run-document with describe")


def test_run_document_respects_allowed_runs_root() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
        _write_case(
            cases_root,
            allrun="#!/bin/sh\nmkdir -p postProcessing 0.001\ntouch postProcessing/runDocCase_1.txt 0.001/Vm 0.001/AV_Ta\nprintf 'ran\\n'\n",
            steps=[{"id": "run", "command": "Allrun", "depends_on": []}],
        )
        doc_path = cases_root / "run.json"
        _plan_to_file(cases_root, doc_path)

        # Allowed root that does NOT contain the case -> rejected before running.
        other_root = cases_root / "somewhere-else"
        other_root.mkdir()
        out = StringIO()
        with redirect_stdout(out), mock.patch.dict(
            os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(other_root)}
        ):
            code = main(["run", "--run-document", str(doc_path)])
        payload = json.loads(out.getvalue())
        assert code != 0, payload
        codes = {d.get("code") for d in payload.get("diagnostics", [])}
        assert "case_root_outside_allowed_root" in codes

        # Allowed root that DOES contain the case -> runs to completion.
        out = StringIO()
        with redirect_stdout(out), mock.patch.dict(
            os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(cases_root)}
        ):
            code = main(["run", "--run-document", str(doc_path)])
        payload = json.loads(out.getvalue())
        assert code == 0, payload
        assert payload["status"] == "ok"


@pytest.fixture
def invalid_run_document_report() -> dict:
    """Run the ``--run-document`` path against a document with a known-bad ``config`` phase slice and return the parsed JSON payload."""
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text(json.dumps({
            "version": "3",
            "id": "d",
            "name": "bad-config",
            "status": "planned",
            "config": {
                "anatomy": "not-an-object",
                "physics": {},
                "stimulus": {},
                "solver": {},
            },
            "configurationSource": "document",
            "launch": {},
            "workflowDag": None,
        }))

        out = StringIO()
        with redirect_stdout(out):
            main(["run", "--run-document", str(doc_path)])
        return json.loads(out.getvalue())


def test_every_diagnostic_carries_the_same_five_fields(invalid_run_document_report) -> None:
    """Reads the flat ``diagnostics`` list the ``--run-document`` CLI path emits, not ``StrictPlanningReport``'s three-key shape."""
    expected = {"level", "code", "message", "source", "field"}
    diagnostics = invalid_run_document_report["diagnostics"]
    assert diagnostics, invalid_run_document_report
    for item in diagnostics:
        assert set(item) == expected, (
            f"diagnostics entry {item!r} has fields {sorted(item)}, "
            f"expected {sorted(expected)}"
        )
    codes = {d["code"] for d in diagnostics}
    assert "run_validation" in codes, diagnostics
    assert "missing_workflow_dag" in codes, diagnostics
    assert "missing_case_root" in codes, diagnostics
