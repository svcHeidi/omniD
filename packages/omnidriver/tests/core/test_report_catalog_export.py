"""Tests for the report-catalog exporter.

Backend Python declares report *definitions* (id, title, kind, URL template,
the ``applicable_when`` predicate, and a default-visible flag); the exporter
serializes them to JSON. The Python side never substitutes ``{port}`` or
``{kind}``, so 4Dpapers (or any future report backend) is swappable without
re-exporting.

For v1 the URL template is ``http://localhost:{port}/{kind}`` (no
``{runId}`` — the user's 4Dpapers app does not route by run yet). The
``applicable_when`` predicate language is flat key-equality:
``None`` ⇒ always applicable, ``{"phase.field": value}`` ⇒ AND of
equality checks. Anything else is invalid and the v1 evaluator throws.

The four subprocess tests that exercised
``scripts/export-report-catalog.py`` moved to
``packages/omnidriver-cardiacfoam/tests/test_report_catalog_export.py``
(Part A, test-ownership split): that script resolves a driver context and
exports cardiacFoam's report catalog specifically, so those assertions
are only non-vacuous against real cardiac content. What remains here is
pure ``matches()`` predicate logic with no plugin dependency.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# applicable_when evaluator (the v1 predicate language)
# ---------------------------------------------------------------------------


def test_applicable_when_none_matches_anything():
    from omnidriver.core.report_catalog import matches

    assert matches(None, {"physics": {"ionic_model": "TenTusscher"}}) is True


def test_applicable_when_flat_equality_matches():
    from omnidriver.core.report_catalog import matches

    pred = {"physics.ionic_model": "TenTusscher"}
    cfg = {"physics": {"ionic_model": "TenTusscher"}}
    assert matches(pred, cfg) is True


def test_applicable_when_flat_equality_rejects_mismatch():
    from omnidriver.core.report_catalog import matches

    pred = {"physics.ionic_model": "TenTusscher"}
    cfg = {"physics": {"ionic_model": "FentonKarma"}}
    assert matches(pred, cfg) is False


def test_applicable_when_multi_key_is_AND():
    from omnidriver.core.report_catalog import matches

    pred = {
        "physics.ionic_model": "TenTusscher",
        "anatomy.mesh": "biventricular",
    }
    cfg = {
        "physics": {"ionic_model": "TenTusscher"},
        "anatomy": {"mesh": "biventricular"},
    }
    assert matches(pred, cfg) is True
    cfg["anatomy"]["mesh"] = "single-cell"
    assert matches(pred, cfg) is False


def test_applicable_when_missing_path_is_not_a_match():
    from omnidriver.core.report_catalog import matches

    pred = {"physics.ionic_model": "TenTusscher"}
    cfg = {"physics": {}}
    assert matches(pred, cfg) is False


def test_applicable_when_unknown_operator_raises():
    """v2 may add operators; v1 must refuse silently-mis-filtering."""
    import pytest

    from omnidriver.core.report_catalog import matches

    pred = {"physics.ionic_model": {"$in": ["TenTusscher"]}}
    with pytest.raises(ValueError, match="unsupported"):
        matches(pred, {"physics": {"ionic_model": "TenTusscher"}})
