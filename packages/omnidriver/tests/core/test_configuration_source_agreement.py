"""Step 4c (docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md):
planning and execution must agree on where a RunDocument's configuration
lives, via the ONE shared decision both call
(``core.runtime.configuration_source.resolve_configuration_source``).

Before this field existed, planning (``run_document_adapter``) inferred
"generic case" from ``spec.metadata`` and execution (``run_document_exec``)
could not see that marker at all, so it validated an intentionally-empty
generic-case/tutorial-record config against the plugin schema unconditionally
and refused every such run (recorded at the end of step 4b). These tests
cover all three entry kinds the design names, plus the smuggling refusal an
ingested document must not evade.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime import record_execution
from omnidriver.core.runtime.configuration_source import resolve_configuration_source
from omnidriver.core.runtime.run_document_adapter import _run_document_from_case
from omnidriver.core.runtime.run_document_exec import build_execution_inputs
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from plugins.declared_case_plugin import DeclaredCasePlugin
from plugins.minimal_plugin import MinimalTestPlugin


def _launch_for(case_root: Path) -> dict:
    return {
        "action": "run",
        "command": [],
        "command_display": "",
        "workflow_state_path": str(case_root / "outputs" / "workflow_state.json"),
        "case_root": str(case_root),
        "setup_root": str(case_root),
        "output_dir": str(case_root / "outputs"),
    }


# ---------------------------------------------------------------------------
# Entry kind 1: a generic case folder (no registered dictionary files present)
# -- configurationSource must be "case", and its (empty) config must not be
# re-checked against the plugin schema at either planning or execution.
# ---------------------------------------------------------------------------


def test_generic_case_entry_is_case_sourced_at_planning_and_execution(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    (case_root / "run-test-case").write_text("#!/bin/sh\nexit 0\n")

    context = driver_context(DeclaredCasePlugin(), source="test:generic-case")
    report = strict_plan(
        "plainCase", overrides={"cases_root": str(tmp_path)}, driver_context=context,
    )

    assert report.status == "ok", report.validation_diagnostics
    run_doc = report.run_document
    assert run_doc.configurationSource == "case"

    # Execution must reach the same "no document config to check" conclusion
    # this document itself already states -- not re-derive it, and not
    # refuse it as a contradiction (its config really is empty).
    inputs, diagnostics = build_execution_inputs(run_doc, driver_context=context)
    assert inputs is not None, diagnostics
    codes = {d.code for d in diagnostics}
    assert "case_configuration_source_carries_config" not in codes
    assert "plugin_config_schema_violation" not in codes


# ---------------------------------------------------------------------------
# Entry kind 2: a tutorial record's committed case (already validated and
# written by commit_record_case before planning ever builds this spec) --
# same configurationSource as a generic case, per the design's own §3 ("a
# tutorial is a data record ... it writes nothing").
# ---------------------------------------------------------------------------


def test_tutorial_record_entry_is_case_sourced(tmp_path: Path) -> None:
    record = TutorialRecord(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        allowed_axes=frozenset(),
        workflow_steps=(WorkflowStep(step_id="solve", command=("run-test-case",)),),
    )
    staged = tmp_path / "case"
    staged.mkdir()
    (staged / "run-test-case").write_text("#!/bin/sh\nexit 0\n")
    spec = record_execution.record_case_spec(
        record,
        case_id="case_0001",
        staged_case_root=staged,
        workflow_step_ids=("solve",),
        command_arguments={},
    )
    assert spec.metadata["generic_case"] is True  # the fact this step reads

    context = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test:tutorial-record",
    )
    workflow_dag = spec.metadata["workflow_dag"]
    # workflow_state=None: this test is about configurationSource, not
    # resume evidence -- `_run_document_from_case` accepts None (the field
    # is nullable) and this sidesteps validate_resume's own, unrelated
    # identity check on an embedded state.
    run_doc, diagnostics = _run_document_from_case(
        entry="case_0001",
        spec=spec,
        launch=_launch_for(staged),
        workflow_dag=workflow_dag,
        workflow_state=None,
        expected_artifacts=(),
        driver_context=context,
    )

    assert run_doc.configurationSource == "case"
    assert run_doc.config == {}
    assert not any(d.level == "error" for d in diagnostics), diagnostics

    inputs, exec_diagnostics = build_execution_inputs(run_doc, driver_context=context)
    assert inputs is not None, exec_diagnostics
    codes = {d.code for d in exec_diagnostics}
    assert "case_configuration_source_carries_config" not in codes
    assert "plugin_config_schema_violation" not in codes


# ---------------------------------------------------------------------------
# Entry kind 3: a factory tutorial with a real, catalog-backed config --
# configurationSource must be "document", and both validate_run and the
# plugin's declared schema must still apply (unlike the two case-sourced
# kinds above).
# ---------------------------------------------------------------------------


def test_factory_tutorial_entry_is_document_sourced() -> None:
    """``singleCell`` is a registered factory tutorial (§3: "a tutorial is a
    data record" is the record shape; a factory tutorial's config lives in
    the document). This test has no real native case on disk (no
    ``cases_root`` points at the monorepo), so planning itself fails on
    missing case files -- but that failure is exactly the proof this test
    wants: ``validate_run`` (``run_validation`` diagnostics, naming real
    cardiac catalog fields like ``myocardiumSolver``) ran at all, which only
    happens when ``configurationSource`` is "document". A case-sourced entry
    (the two tests above) never produces these codes."""
    cardiacfoam = pytest.importorskip("omnidriver.cardiacfoam.cardiacfoam_plugin")
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    context = driver_context(
        OpenFOAMEnvironmentPlugin(), cardiacfoam.CardiacFoamPlugin(),
        source="test:factory-tutorial",
    )
    report = strict_plan("singleCell", driver_context=context)

    assert report.run_document is not None
    run_doc = report.run_document
    assert run_doc.configurationSource == "document"

    codes = {d.code for d in report.validation_diagnostics}
    assert "run_validation" in codes, report.validation_diagnostics
    assert any(
        d.code == "run_validation" and "myocardiumSolver" in d.message
        for d in report.validation_diagnostics
    ), report.validation_diagnostics
    assert "case_configuration_source_carries_config" not in codes


# ---------------------------------------------------------------------------
# The untrusted-ingestion claim: an agent-authored document cannot use
# "case" to smuggle unvalidated document config past the plugin schema
# check, and the plugin-identity gate still applies regardless of source.
# ---------------------------------------------------------------------------


def test_case_source_cannot_smuggle_unvalidated_config_past_execution(
    tmp_path: Path,
) -> None:
    from omnidriver.core.runtime.run_model import RunDocument

    case_root = tmp_path / "case"
    case_root.mkdir()
    (case_root / "run-test-case").write_text("#!/bin/sh\nexit 0\n")
    context = driver_context(MinimalTestPlugin(entrypoint="run-test-case"), source="test")

    run_doc = RunDocument(
        id="attacker-document",
        name="attacker-document",
        status="planned",
        config={"solver": {"reallyImportantSafetyCheck": "disabled"}},
        configurationSource="case",
        plugin=context.identity.to_json(),
        workflowDag={"steps": [{"id": "run", "command": "run-test-case", "depends_on": []}]},
        launch={"caseRoot": str(case_root), "outputDir": str(case_root / "out")},
    )

    inputs, diagnostics = build_execution_inputs(run_doc, driver_context=context)

    assert inputs is None
    codes = {d.code for d in diagnostics}
    assert "case_configuration_source_carries_config" in codes


def test_resolve_configuration_source_is_the_single_decision_point() -> None:
    """A direct unit check of the shared function itself, independent of
    either caller -- the contract both `run_document_adapter` and
    `run_document_exec` must keep matching."""
    document = resolve_configuration_source("document", {"a": "1"})
    assert document.validate_document_config is True
    assert document.diagnostics == ()

    empty_case = resolve_configuration_source("case", {})
    assert empty_case.validate_document_config is False
    assert empty_case.diagnostics == ()

    shell_case = resolve_configuration_source(
        "case", {"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}},
    )
    assert shell_case.validate_document_config is False
    assert shell_case.diagnostics == ()

    contradiction = resolve_configuration_source("case", {"a": "1"})
    assert contradiction.validate_document_config is False
    assert [d.code for d in contradiction.diagnostics] == [
        "case_configuration_source_carries_config",
    ]

    unknown = resolve_configuration_source("nowhere", {})
    assert unknown.validate_document_config is False
    assert [d.code for d in unknown.diagnostics] == ["unknown_configuration_source"]

    missing = resolve_configuration_source(None, {})
    assert missing.validate_document_config is False
    assert [d.code for d in missing.diagnostics] == ["unknown_configuration_source"]
