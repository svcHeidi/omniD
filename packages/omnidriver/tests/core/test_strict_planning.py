from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.plugin_interface import generic_openfoam_context
from omnidriver.core.strict_planning import (
    StrictPlanReport,
    _is_nondimensional_entry,
    _mesh_geometry_diagnostics,
)


def test_report_has_mesh_geometry_field() -> None:
    report = StrictPlanReport(status="ok", entry="x", resolved_entry={})
    payload = report.to_json()
    assert "mesh_geometry_diagnostics" in payload
    assert payload["mesh_geometry_diagnostics"] == []
    assert payload["readiness_score"] == {}
    assert payload["simulation_audit"] == []


def test_mesh_gate_skipped_by_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    assert _mesh_geometry_diagnostics(tmp_path) == ()


def test_manufactured_entry_is_nondimensional(tmp_path: Path) -> None:
    spec = SimpleNamespace(
        case_root=str(tmp_path),
        metadata={"entry_name": "manufacturedBidomain"},
    )
    assert _is_nondimensional_entry(spec) is True


def test_plain_entry_is_dimensional(tmp_path: Path) -> None:
    spec = SimpleNamespace(
        case_root=str(tmp_path),
        metadata={"entry_name": "singleCell", "workflow_family": "tutorial"},
    )
    assert _is_nondimensional_entry(spec, driver_context=generic_openfoam_context()) is False


def test_dictionary_resolution_audit_text_is_plugin_neutral_for_non_cardiac_plugin(
    tmp_path: Path,
) -> None:
    """P2.7: the dictionary_resolution audit stage's success text must come
    from the active plugin, not a core-hardcoded cardiac sentence. A
    non-cardiac plugin must not see "electroProperties"/"physicsProperties"
    in its own audit text."""
    from omnidriver.core.runtime.strict_audit import _build_simulation_audit
    from omnidriver.core.plugin_interface import driver_context
    from plugins.minimal_plugin import MinimalOpenFOAMPlugin

    context = driver_context(MinimalOpenFOAMPlugin(), source="test:minimal")
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
