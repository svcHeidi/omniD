"""OpenFOAM strict-planning conventions are adapter-owned."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.strict_planning import _is_nondimensional_entry, _mesh_geometry_diagnostics
from omnidriver.openfoam.environment import openfoam_environment_context


def test_mesh_gate_skipped_by_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    assert _mesh_geometry_diagnostics(tmp_path, driver_context=openfoam_environment_context()) == ()


def test_manufactured_entry_is_nondimensional(tmp_path: Path) -> None:
    spec = SimpleNamespace(case_root=str(tmp_path), metadata={"entry_name": "manufacturedBidomain"})
    assert _is_nondimensional_entry(spec, driver_context=openfoam_environment_context()) is True


def test_plain_entry_is_dimensional(tmp_path: Path) -> None:
    spec = SimpleNamespace(
        case_root=str(tmp_path), metadata={"entry_name": "singleCell", "workflow_family": "tutorial"},
    )
    assert _is_nondimensional_entry(spec, driver_context=openfoam_environment_context()) is False
