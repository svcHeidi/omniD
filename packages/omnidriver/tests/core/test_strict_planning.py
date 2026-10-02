from __future__ import annotations

from omnidriver.core.strict_planning import StrictPlanReport


def test_report_carries_one_plugin_diagnostics_family() -> None:
    payload = StrictPlanReport(status="ok", entry="x", resolved_entry={}).to_json()
    assert payload["plugin_diagnostics"] == []
    assert payload["readiness_score"] == {}
    assert payload["simulation_audit"] == []
    for retired in (
        "mesh_geometry_diagnostics", "function_object_diagnostics",
        "case_dict_key_diagnostics", "catalog_coverage_errors", "validation_diagnostics",
    ):
        assert retired not in payload
