"""A stage that did not run may not earn points.

See docs/superpowers/specs/2026-09-18-coverage-as-evidence.md.

`_score_from_diagnostics` branches on error, then on warning, then falls through
to `status="passed", points=max_points`. Every skip path in the codebase returns
an empty diagnostic tuple, which lands on that fallthrough -- so a check that
never executed is scored identically to one that ran clean.

These tests use `DeclaredCasePlugin`, a neutral test plugin, deliberately.
The semantics are core's and must be demonstrable without either cardiac
adapter; a cardiac plugin here would make core's rule look like a cardiac one.

Note that core's own conftest sets `SKIP_ENV_DIAGNOSTICS` for the whole suite,
so `environment_preflight` is already suppressed in every core test. It has been
scoring 10/10 throughout.
"""
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


def test_an_uncovered_stage_is_named_in_the_score(tmp_path: Path) -> None:
    """Which stage went unchecked has to be recoverable from the report.

    A lower percentage tells a reader something is missing but not what, and
    the whole point is that an absence carries its reason.
    """
    report = _plan(tmp_path)

    assert "environment_preflight" in report.readiness_score.get("uncovered_stages", ()), (
        "readiness_score names blocked and warning stages but has no way to "
        f"name an uncovered one: {sorted(report.readiness_score)}"
    )
