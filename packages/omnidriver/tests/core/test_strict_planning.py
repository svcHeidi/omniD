from __future__ import annotations

from types import SimpleNamespace

from omnidriver.core.strict_planning import (
    StrictPlanReport,
)


def test_report_has_mesh_geometry_field() -> None:
    report = StrictPlanReport(status="ok", entry="x", resolved_entry={})
    payload = report.to_json()
    assert "mesh_geometry_diagnostics" in payload
    assert payload["mesh_geometry_diagnostics"] == []
    assert payload["readiness_score"] == {}
    assert payload["simulation_audit"] == []


def test_dictionary_resolution_audit_text_is_plugin_neutral_for_non_cardiac_plugin(
    tmp_path: Path,
) -> None:
    """Dictionary-resolution audit text comes from the active plugin."""
    from omnidriver.core.runtime.strict_audit import _build_simulation_audit
    from omnidriver.core.plugin_interface import driver_context
    from plugins.minimal_plugin import MinimalTestPlugin

    context = driver_context(MinimalTestPlugin(), source="test:minimal")
    spec = SimpleNamespace(
        case_root=tmp_path,
        metadata={},  # not a generic_case, exercises the plugin-sourced branch
        build_cases=lambda: [],
    )

    audit_items, _generation_diagnostics, _readiness = _build_simulation_audit(
        spec=spec,
        driver_context=context,
        workflow_dag=None,
        artifacts=(),
        validation_diagnostics=(),
        workflow_diagnostics=(),
        artifact_diagnostics=(),
        environment_diagnostics=(),
        mesh_geometry_diagnostics=(),
    )

    resolution_item = next(
        item for item in audit_items if item.stage == "dictionary_resolution"
    )
    assert "electroProperties" not in resolution_item.summary
    assert "physicsProperties" not in resolution_item.summary
