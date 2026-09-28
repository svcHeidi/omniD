"""A stage that did not run may not earn points."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from plugins.declared_case_plugin import DeclaredCasePlugin


def _plan(tmp_path: Path):
    case_root = tmp_path / "plainCase"
    case_root.mkdir()
    (case_root / "run-test-case").write_text("#!/bin/sh\nexit 0\n")
    return strict_plan(
        "plainCase",
        overrides={"cases_root": str(tmp_path)},
        driver_context=driver_context(DeclaredCasePlugin(), source="test:coverage"),
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


def test_a_generic_case_reports_inapplicable_checks_as_such(tmp_path: Path) -> None:
    """A generic case has no plugin dictionaries; saying `passed` claims it did."""
    report = _plan(tmp_path)

    assert _stage(report, "case_preparation_files").status == "not_applicable"
    assert _stage(report, "dictionary_resolution").status == "not_applicable"


def test_an_exempt_mesh_check_is_reported_as_inapplicable(tmp_path: Path) -> None:
    """`_mesh_geometry_diagnostics` returns () for two unrelated reasons."""
    report = _plan(tmp_path)

    assert _stage(report, "mesh_geometry").status == "not_applicable"


def test_an_inapplicable_check_leaves_the_denominator(tmp_path: Path) -> None:
    """`not_applicable` is not a failure to cover; it is nothing to cover."""
    report = _plan(tmp_path)
    readiness = report.readiness_score

    inapplicable = sum(
        item.max_points for item in report.simulation_audit
        if item.status == "not_applicable"
    )
    assert inapplicable > 0, "this plan was expected to have inapplicable stages"

    assert readiness["max_score"] == 85 - inapplicable, (
        "an inapplicable stage is still being counted as something this plan "
        "owed and did not deliver"
    )
    # The suppressed one stays in: it was owed and was not done.
    assert _stage(report, "environment_preflight").max_points == 10
    assert "environment_preflight" in readiness["uncovered_stages"]


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
