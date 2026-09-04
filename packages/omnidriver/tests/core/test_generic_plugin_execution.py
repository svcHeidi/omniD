from __future__ import annotations

import os
import stat
import json
from pathlib import Path

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.run_document_exec import build_execution_inputs
from omnidriver.core.runtime.run_model import RunDocument
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def test_generic_plugin_executes_plain_allrun_case(tmp_path: Path) -> None:
    # ``--plugin none`` resolves to the built-in GenericOpenFOAMPlugin, whose
    # legacy_environment_diagnostics fallback reaches omnidriver.openfoam
    # unconditionally (an ungated core default, not cardiac-specific -- see
    # ENVIRONMENT_CONTRACT.md sec.4). Swapped to a trusted-import plugin that
    # answers the environment hooks itself so this exercises the CLI
    # execution path without needing omnidriver.openfoam installed.
    case_root = tmp_path / "plainOpenFoamCase"
    case_root.mkdir()
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nprintf complete > generic-proof.txt\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    exit_code = main([
        "run",
        "--strict",
        "--plugin",
        "plugins.neutral_environment_plugin:_GenericOpenFOAMPluginWithNeutralEnvironment",
        "--entry", "plainOpenFoamCase",
        "--cases-root", str(tmp_path),
    ])

    assert exit_code == 0
    assert (case_root / "generic-proof.txt").read_text() == "complete"
    assert (case_root / "postProcessing" / "workflow_state.json").is_file()


def test_trusted_minimal_plugin_executes_plain_allrun_case(
    tmp_path: Path,
    capsys,
) -> None:
    # MinimalOpenFOAMPlugin's environment-diagnostics fallback also reaches
    # omnidriver.openfoam unconditionally; swapped to NeutralEnvironmentPlugin,
    # which answers get_environment_diagnostics() -> () itself.
    case_root = tmp_path / "plainOpenFoamCase"
    case_root.mkdir()
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nprintf minimal > minimal-proof.txt\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    exit_code = main([
        "run",
        "--strict",
        "--plugin",
        "plugins.neutral_environment_plugin:NeutralEnvironmentPlugin",
        "--entry", "plainOpenFoamCase",
        "--cases-root", str(tmp_path),
    ])

    assert exit_code == 0
    assert (case_root / "minimal-proof.txt").read_text() == "minimal"
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"


def test_run_document_validation_uses_the_selected_plugin(tmp_path: Path) -> None:
    case_root = tmp_path / "plainOpenFoamCase"
    case_root.mkdir()
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nexit 0\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    context = driver_context(MinimalOpenFOAMPlugin(), source="test")
    run_doc = RunDocument(
        id="minimal-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=context.identity.to_json(),
        config={"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
        workflowDag={
            "steps": [{"id": "run", "command": "Allrun", "depends_on": []}],
        },
        launch={
            "caseRoot": str(case_root),
            "outputDir": str(case_root / "postProcessing"),
        },
    )

    inputs, diagnostics = build_execution_inputs(
        run_doc, driver_context=context,
    )

    assert inputs is not None, diagnostics
    assert not [item for item in diagnostics if item["code"] == "run_validation"]


def test_run_document_rejects_a_mismatched_supplied_plugin(tmp_path: Path) -> None:
    case_root = tmp_path / "plainOpenFoamCase"
    case_root.mkdir()
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nexit 0\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    context = driver_context(MinimalOpenFOAMPlugin(), source="test")
    planned_plugin = context.identity.to_json() | {"capability_digest": "sha256:wrong"}
    run_doc = RunDocument(
        id="mismatched-plugin-document",
        name="plainOpenFoamCase",
        status="planned",
        plugin=planned_plugin,
        config={"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
        workflowDag={"steps": [{"id": "run", "command": "Allrun", "depends_on": []}]},
        launch={
            "caseRoot": str(case_root),
            "outputDir": str(case_root / "postProcessing"),
        },
    )

    inputs, diagnostics = build_execution_inputs(
        run_doc, driver_context=context,
    )

    assert inputs is None
    assert [item["code"] for item in diagnostics] == ["plugin_identity_mismatch"]
