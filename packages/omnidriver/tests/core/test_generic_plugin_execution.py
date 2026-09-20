from __future__ import annotations

import os
import stat
import json
from pathlib import Path

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.run_document_exec import build_execution_inputs
from omnidriver.core.runtime.run_model import RunDocument
from plugins.minimal_plugin import MinimalTestPlugin


def test_trusted_neutral_plugin_executes_its_declared_case_script(
    tmp_path: Path,
    capsys,
) -> None:
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nprintf neutral > neutral-proof.txt\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    exit_code = main([
        "run",
        "--strict",
        "--plugin",
        "plugins.declared_case_plugin:DeclaredCasePlugin",
        "--entry", "plainCase",
        "--cases-root", str(tmp_path),
    ])

    assert exit_code == 0
    assert (case_root / "neutral-proof.txt").read_text() == "neutral"
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"


def test_run_document_validation_uses_the_selected_plugin(tmp_path: Path) -> None:
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    script = case_root / "run-test-case"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    context = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    )
    run_doc = RunDocument(
        id="minimal-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=context.identity.to_json(),
        config={"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
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
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    )
    planned_plugin = context.identity.to_json() | {"capability_digest": "sha256:wrong"}
    run_doc = RunDocument(
        id="mismatched-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=planned_plugin,
        config={"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
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
    # Corrected 2026-09-20 (Phase 0 Task 10): diagnostics are now the
    # canonical `StrictDiagnostic` dataclass, not `{code: ...}` dicts.
    assert [item.code for item in diagnostics] == ["plugin_identity_mismatch"]
