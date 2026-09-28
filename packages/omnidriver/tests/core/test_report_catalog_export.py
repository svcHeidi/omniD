"""Tests for the report-catalog exporter."""

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
