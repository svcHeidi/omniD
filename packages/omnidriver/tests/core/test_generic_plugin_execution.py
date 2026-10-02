from __future__ import annotations

import stat
import json
from pathlib import Path

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.run_document_exec import build_execution_inputs
from omnidriver.core.runtime.run_model import RunDocument
from plugins.toy import ToyProvider


def test_trusted_neutral_plugin_executes_its_declared_case_script(
    tmp_path: Path,
    capsys,
) -> None:
    case_root = tmp_path / "cases" / "plainCase"
    case_root.mkdir(parents=True)
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nprintf neutral > neutral-proof.txt\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    exit_code = main([
        "run",
        "--strict",
        "--plugin",
        "plugins.toy:E2EFolderPlugin",
        "--case", str(case_root),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])

    assert exit_code == 0
    assert (tmp_path / "scratch" / "records" / "plainCase" / "neutral-proof.txt").read_text() == "neutral"
    assert not (case_root / "neutral-proof.txt").exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"


def test_run_document_validation_uses_the_selected_plugin(tmp_path: Path) -> None:
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    context = driver_context(
        ToyProvider(entrypoint="run-test-case"), source="test"
    )
    run_doc = RunDocument(
        id="minimal-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=context.identity.to_json(),
        workflowDag={
            "steps": [{"id": "run", "command": "run-test-case", "depends_on": []}],
        },
        launch={
            "caseRoot": str(case_root),
            "outputDir": str(case_root / "outputs"),
        },
    )

    inputs, diagnostics = build_execution_inputs(
        run_doc, driver_context=context,
    )

    assert inputs is not None, diagnostics
    assert not [item for item in diagnostics if item["code"] == "run_validation"]


def test_run_document_rejects_a_mismatched_supplied_plugin(tmp_path: Path) -> None:
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    context = driver_context(
        ToyProvider(entrypoint="run-test-case"), source="test"
    )
    planned_plugin = context.identity.to_json() | {"capability_digest": "sha256:wrong"}
    run_doc = RunDocument(
        id="mismatched-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=planned_plugin,
        workflowDag={"steps": [{"id": "run", "command": "run-test-case", "depends_on": []}]},
        launch={
            "caseRoot": str(case_root),
            "outputDir": str(case_root / "outputs"),
        },
    )

    inputs, diagnostics = build_execution_inputs(
        run_doc, driver_context=context,
    )

    assert inputs is None
    # Diagnostics are the canonical StrictDiagnostic dataclass, not {code: ...} dicts.
    assert [item.code for item in diagnostics] == ["plugin_identity_mismatch"]


def test_cli_context_from_run_document_rejects_a_mismatched_supplied_plugin(
    tmp_path: Path, capsys,
) -> None:
    """Pins the top-level error message from `_context_from_run_document`'s own identity gate, since `result is None` alone would also pass via `build_execution_inputs`'s twin gate."""
    import argparse

    from omnidriver.cli import _context_from_run_document

    context = driver_context(
        ToyProvider(entrypoint="run-test-case"), source="test"
    )
    selected = context.identity.to_json()
    planned_plugin = selected | {
        "resolutions": {**selected["resolutions"], "manifest": "org.some.other.provider"},
    }
    # The identity gate runs, and returns, before `workflowDag`/`launch` are
    # ever consulted, so a minimal (schema-valid) document is enough here --
    # unlike `test_run_document_rejects_a_mismatched_supplied_plugin` above,
    # which exercises `build_execution_inputs` downstream of that gate and
    # needs a real workflow DAG and launch block.
    run_doc = RunDocument(
        id="mismatched-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=planned_plugin,
    )
    doc_path = tmp_path / "run_document.json"
    doc_path.write_text(json.dumps(run_doc.to_json()))

    args = argparse.Namespace(
        run_document=str(doc_path), environment_source=None,
    )
    result = _context_from_run_document(args, context)
    printed = json.loads(capsys.readouterr().out)

    # Not just "returned None" -- the identity gate itself must be what
    # rejected it, naming `resolutions` as the field that moved. Without
    # the fix, `mismatched` stays empty here (every compared key is a dead
    # `None != None` or an unchanged digest) and this document falls through
    # to fail later, for an unrelated reason (no `workflowDag`), which would
    # also make `result is None` true for the wrong cause.
    assert result is None
    assert "does not match the selected plugin" in printed.get("error", "")
    assert "resolutions" in printed["error"]
