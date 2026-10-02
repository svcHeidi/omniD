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


def test_a_suppressed_environment_preflight_earns_no_points(tmp_path: Path) -> None:
    """The stage records that it was skipped, then is paid in full for it."""
    report = _plan(tmp_path)
    item = _stage(report, "environment_preflight")

    # Precondition: this really is the suppressed path, not a stage that ran.
    assert item.evidence["skipped"] is True, (
        "expected SKIP_ENV_DIAGNOSTICS to be in force from core's conftest; "
        "without it this test proves nothing"
    )

    assert item.points == 0, (
        f"environment_preflight was skipped and still earned {item.points} of "
        f"{item.max_points} points with status {item.status!r}"
    )


def test_a_suppressed_stage_is_not_reported_as_passed(tmp_path: Path) -> None:
    """`passed` must mean a check ran and found nothing wrong."""
    report = _plan(tmp_path)
    item = _stage(report, "environment_preflight")

    assert item.status != "passed", (
        "a stage that did not execute reports the same status as one that ran "
        "clean, so the two are indistinguishable to any reader"
    )


def test_a_suppressed_stage_does_not_reach_a_perfect_score(tmp_path: Path) -> None:
    """The aggregate is the thing that misleads, so assert on it directly."""
    report = _plan(tmp_path)

    assert report.readiness_score["percent"] < 100, (
        "a plan with a suppressed environment preflight reports "
        f"{report.readiness_score['percent']}% ready"
    )


def test_only_the_stages_every_solver_has_are_scored(tmp_path: Path) -> None:
    """A check that depends on a solver's file formats is a plugin diagnostic, not a stage."""
    report = _plan(tmp_path)

    assert [item.stage for item in report.simulation_audit] == [
        "workflow_preparation", "artifact_prediction", "environment_preflight",
    ]
    assert report.readiness_score["max_score"] == 45
    assert "inapplicable_stages" not in report.readiness_score


def test_a_partially_covered_plan_is_not_ready(tmp_path: Path) -> None:
    """`ready` is a success claim, and success over unrun checks is the defect."""
    report = _plan(tmp_path)

    assert report.readiness_score["uncovered_stages"], (
        "precondition: this plan must have an uncovered stage"
    )
    assert report.readiness_score["status"] != "ready"


def test_an_uncovered_stage_is_named_in_the_score(tmp_path: Path) -> None:
    """Which stage went unchecked has to be recoverable from the report."""
    report = _plan(tmp_path)

    assert "environment_preflight" in report.readiness_score.get("uncovered_stages", ()), (
        "readiness_score names blocked and warning stages but has no way to "
        f"name an uncovered one: {sorted(report.readiness_score)}"
    )
