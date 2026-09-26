"""Pure-function tests for ``opencarp_native``'s test helpers themselves --
no binary, no tutorials tree needed."""
from __future__ import annotations

from opencarp_native import LAT_PATH, _only_a_declared_artifact_is_missing

_BASE = {"status": "failed", "materialization_error": None, "plan_error": None, "timeout_error": None}


def _case(**reconciliation_kwargs):
    return {**_BASE, "artifact_reconciliation": {"missing_count": 1, **reconciliation_kwargs}}


def test_only_the_lat_artifact_missing_is_tolerated():
    case = _case(artifacts=[{"artifact_id": "record.solve.2", "predicted_path": LAT_PATH, "status": "missing"}])
    assert _only_a_declared_artifact_is_missing(case) is True


def test_a_different_missing_artifact_stays_fatal():
    """M11, controller review 2026-09-26: this used to accept ANY missing
    declared artifact; a missing out/vm.igb (an actual defect) must not be
    tolerated just because F17's opt-in is set."""
    case = _case(artifacts=[{"artifact_id": "record.solve.5", "predicted_path": "out/vm.igb", "status": "missing"}])
    assert _only_a_declared_artifact_is_missing(case) is False


def test_the_lat_artifact_plus_another_missing_artifact_stays_fatal():
    case = _case(artifacts=[
        {"artifact_id": "record.solve.2", "predicted_path": LAT_PATH, "status": "missing"},
        {"artifact_id": "record.solve.5", "predicted_path": "out/vm.igb", "status": "missing"},
    ])
    assert _only_a_declared_artifact_is_missing(case) is False


def test_a_status_other_than_failed_is_never_tolerated_here():
    case = {**_BASE, "status": "completed", "artifact_reconciliation": {
        "missing_count": 1, "artifacts": [{"artifact_id": "record.solve.2", "predicted_path": LAT_PATH, "status": "missing"}],
    }}
    assert _only_a_declared_artifact_is_missing(case) is False


def test_a_materialization_error_is_never_tolerated_here():
    case = _case(artifacts=[{"artifact_id": "record.solve.2", "predicted_path": LAT_PATH, "status": "missing"}])
    case["materialization_error"] = "boom"
    assert _only_a_declared_artifact_is_missing(case) is False
