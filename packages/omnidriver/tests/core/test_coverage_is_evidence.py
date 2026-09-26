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


def test_a_generic_case_reports_inapplicable_checks_as_such(tmp_path: Path) -> None:
    """A generic case has no plugin dictionaries; saying `passed` claims it did.

    Both stages already know: case_preparation_files records
    ``generic_case: True`` in its evidence, and dictionary_resolution's own
    success summary reads "The generic case needs no plugin configuration
    parsing." Both then score full points for work they did not do.
    """
    report = _plan(tmp_path)

    assert _stage(report, "case_preparation_files").status == "not_applicable"
    assert _stage(report, "dictionary_resolution").status == "not_applicable"


def test_an_exempt_mesh_check_is_reported_as_inapplicable(tmp_path: Path) -> None:
    """`_mesh_geometry_diagnostics` returns () for two unrelated reasons.

    One is SKIP_GEOMETRY_DIAGNOSTICS (renamed 2026-09-26). The other is
    `exempt`, which is `_mesh_geometry_exempt(...)` (corrected 2026-09-26,
    R1 fix, finding M6: this said "renamed 2026-09-26 from the old
    name-based heuristic" -- it is not a rename. The old name-based
    heuristic, `_is_nondimensional_entry`, was deleted outright; this is a
    behaviour change, exempting a case by the plugin's own hook instead)
    -- a case with no physical mesh scale, or one whose conventions core
    does not know. Both produce an
    empty tuple, so the audit could not tell them apart from a mesh that was
    examined and found clean, and an exempt case kept earning the stage's full
    five points.
    """
    report = _plan(tmp_path)

    assert _stage(report, "mesh_geometry").status == "not_applicable"


def test_an_inapplicable_check_leaves_the_denominator(tmp_path: Path) -> None:
    """`not_applicable` is not a failure to cover; it is nothing to cover.

    A check that could never have applied must not be counted against the plan.
    Keeping it in the denominator would replace paying for work never done with
    penalising a plan for work that was never owed -- the same defect mirrored.
    `not_requested` and `unavailable` stay in, because those are real gaps.
    """
    report = _plan(tmp_path)
    readiness = report.readiness_score

    inapplicable = sum(
        item.max_points for item in report.simulation_audit
        if item.status == "not_applicable"
    )
    assert inapplicable > 0, "this plan was expected to have inapplicable stages"

    assert readiness["max_score"] == 100 - inapplicable, (
        "an inapplicable stage is still being counted as something this plan "
        "owed and did not deliver"
    )
    # The suppressed one stays in: it was owed and was not done.
    assert _stage(report, "environment_preflight").max_points == 10
    assert "environment_preflight" in readiness["uncovered_stages"]


def test_a_partially_covered_plan_is_not_ready(tmp_path: Path) -> None:
    """`ready` is a success claim, and success over unrun checks is the defect.

    A caller branching on status rather than reading the percentage and the
    uncovered list would otherwise behave exactly as it did before any of this.
    """
    report = _plan(tmp_path)

    assert report.readiness_score["uncovered_stages"], (
        "precondition: this plan must have an uncovered stage"
    )
    assert report.readiness_score["status"] != "ready"


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
