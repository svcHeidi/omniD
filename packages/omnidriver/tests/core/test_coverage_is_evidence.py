"""A stage that did not run may not earn points."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import case_folder_record
from plugins.e2e_record_plugin import E2EFolderPlugin


def _plan(tmp_path: Path):
    case_root = tmp_path / "cases" / "plainCase"
    case_root.mkdir(parents=True)
    (case_root / "run-test-case").write_text("#!/bin/sh\nexit 0\n")
    context = driver_context(E2EFolderPlugin(), source="test:coverage")
    record, cases_root = case_folder_record(case_root, driver_context=context)
    return strict_plan(
        record,
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
        driver_context=context,
    )


def _stage(report, name: str):
    return next(item for item in report.simulation_audit if item.stage == name)


def test_only_the_stages_every_solver_has_are_scored(tmp_path: Path) -> None:
    """A check that depends on a solver's file formats is a plugin diagnostic, not a stage."""
    report = _plan(tmp_path)

    assert [item.stage for item in report.simulation_audit] == [
        "workflow_preparation", "artifact_prediction", "environment_preflight",
    ]
    assert report.readiness_score["max_score"] == 45
    assert "inapplicable_stages" not in report.readiness_score
