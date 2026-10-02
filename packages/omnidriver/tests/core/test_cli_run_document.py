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
from conftest import skip_without_repo
pytestmark = [skip_without_repo]

from omnidriver.cli import main

PLUGIN = "plugins.e2e_record_plugin:E2EFolderPlugin"
SCRIPT = "run-test-case"
CASE_SCRIPT = "#!/bin/sh\ntouch ran.marker\nprintf 'ran\\n'\n"


def _write_case(root: Path, *, script: str = CASE_SCRIPT) -> Path:
    case_root = root / "runDocCase"
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "input.txt").write_text("authored\n")
    script_path = case_root / SCRIPT
    script_path.write_text(script)
    os.chmod(script_path, 0o755)
    return case_root


def _plan_to_file(case_root: Path, doc_path: Path, scratch: Path) -> dict:
    """Run `plan --strict --case` and write its run_document to doc_path."""
    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "plan", "--strict", "--plugin", PLUGIN, "--case", str(case_root),
            "--scratch-dir", str(scratch),
        ])
    report = json.loads(out.getvalue())
    assert code == 0, report
    run_document = report["run_document"]
    assert run_document is not None
    doc_path.write_text(json.dumps(run_document))
    return run_document


def test_plan_then_run_document_round_trip_executes(tmp_path) -> None:
    case_root = _write_case(tmp_path / "cases")
    doc_path = tmp_path / "run.json"
    document = _plan_to_file(case_root, doc_path, tmp_path / "scratch")

    out = StringIO()
    with redirect_stdout(out):
        code = main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    payload = json.loads(out.getvalue())
    assert code == 0, payload
    assert payload["status"] == "ok"
    assert payload["workflow_state"]["status"] == "completed"
    assert Path(payload["workflow_state_path"]).exists()
    assert payload["steps"]
    assert payload["steps"][0]["status"] == "ok"
    assert (Path(document["launch"]["caseRoot"]) / "ran.marker").exists()

    case_record_path = Path(payload["case_record_path"])
    assert case_record_path.exists()
    case_record = json.loads(case_record_path.read_text())
    # setup_root flows from the RunDocument's own launch.setupRoot into the
    # standalone case record, the same way it does for a sweep case.
    assert case_record["setup_root"] == document["launch"]["setupRoot"]


def test_step_via_run_document_executes_named_step(tmp_path) -> None:
    case_root = _write_case(tmp_path / "cases")
    doc_path = tmp_path / "run.json"
    _plan_to_file(case_root, doc_path, tmp_path / "scratch")

    out = StringIO()
    with redirect_stdout(out):
        code = main(["step", "--plugin", PLUGIN, "--run-document", str(doc_path), "--step", "run"])

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
            "launch": {},
            "workflowDag": None,
        }))

        out = StringIO()
        with redirect_stdout(out):
            code = main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

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
            code = main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

        payload = json.loads(out.getvalue())
        assert code == 1
        codes = {d["code"] for d in payload["diagnostics"]}
        assert "unknown_workflow_command" in codes


def test_run_document_and_entry_are_mutually_exclusive() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text("{}")
        try:
            main(["run", "--run-document", str(doc_path), "--entry", "toyTutorial"])
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


def test_run_document_respects_allowed_runs_root(tmp_path) -> None:
    case_root = _write_case(tmp_path / "cases")
    doc_path = tmp_path / "run.json"
    _plan_to_file(case_root, doc_path, tmp_path / "scratch")

    # Allowed root that does NOT contain the case -> rejected before running.
    other_root = tmp_path / "somewhere-else"
    other_root.mkdir()
    out = StringIO()
    with redirect_stdout(out), mock.patch.dict(
        os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(other_root)}
    ):
        code = main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    payload = json.loads(out.getvalue())
    assert code != 0, payload
    codes = {d.get("code") for d in payload.get("diagnostics", [])}
    assert "case_root_outside_allowed_root" in codes

    # Allowed root that DOES contain the case -> runs to completion.
    out = StringIO()
    with redirect_stdout(out), mock.patch.dict(
        os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(tmp_path)}
    ):
        code = main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    payload = json.loads(out.getvalue())
    assert code == 0, payload
    assert payload["status"] == "ok"


@pytest.fixture
def invalid_run_document_report() -> dict:
    """Run the ``--run-document`` path against a document with no launch paths and no workflow, and return the parsed JSON payload."""
    with tempfile.TemporaryDirectory() as temp_dir:
        doc_path = Path(temp_dir) / "run.json"
        doc_path.write_text(json.dumps({
            "version": "3",
            "id": "d",
            "name": "bad-document",
            "status": "planned",
            "launch": {},
            "workflowDag": None,
        }))

        out = StringIO()
        with redirect_stdout(out):
            main(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
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
    assert "missing_workflow_dag" in codes, diagnostics
    assert "missing_case_root" in codes, diagnostics
