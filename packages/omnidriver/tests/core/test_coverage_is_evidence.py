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
