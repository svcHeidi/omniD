"""A case is exempt from mesh-scale checks by the plugin's hook, never by its
name (spec 2026-09-26-core-generality-design.md §2, A7)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.core import strict_planning
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.models import TutorialSpec
from plugins.minimal_plugin import MinimalTestPlugin


def _spec(root: Path, **metadata) -> TutorialSpec:
    return TutorialSpec(
        name="t", case_root=root, setup_root=root, output_dir=root,
        build_cases=lambda: [], metadata=dict(metadata),
    )


class _Nondimensional(MinimalTestPlugin):
    def is_nondimensional_case(self, spec):
        return True


class _HasGeometryChecks(MinimalTestPlugin):
    def get_base_mesh_geometry_diagnostics(self, case_root):
        return (SimpleNamespace(level="warning", code="toy_geometry", message="toy", region="r"),)


def test_the_name_heuristic_is_gone():
    assert not hasattr(strict_planning, "_is_nondimensional_entry")


@pytest.mark.parametrize("name", ["manufacturedToy", "toyVerification"])
def test_a_name_no_longer_exempts_a_case(name, tmp_path):
    ctx = driver_context(MinimalTestPlugin(), source="test")
    spec = _spec(tmp_path, entry_name=name, workflow_family=name)
    assert strict_planning._mesh_geometry_exempt(spec, ctx) is False


def test_the_plugin_hook_exempts(tmp_path):
    ctx = driver_context(_Nondimensional(), source="test")
    assert strict_planning._mesh_geometry_exempt(_spec(tmp_path), ctx) is True


def test_a_generic_case_is_exempt(tmp_path):
    ctx = driver_context(MinimalTestPlugin(), source="test")
    assert strict_planning._mesh_geometry_exempt(_spec(tmp_path, generic_case=True), ctx) is True


def test_the_geometry_skip_variable_declines_the_checks(tmp_path, monkeypatch):
    ctx = driver_context(_HasGeometryChecks(), source="test")
    monkeypatch.delenv("SKIP_GEOMETRY_DIAGNOSTICS", raising=False)
    assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) != ()
    monkeypatch.setenv("SKIP_GEOMETRY_DIAGNOSTICS", "1")
    assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) == ()


def test_the_old_variable_name_is_not_read(tmp_path, monkeypatch):
    ctx = driver_context(_HasGeometryChecks(), source="test")
    monkeypatch.delenv("SKIP_GEOMETRY_DIAGNOSTICS", raising=False)
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) != ()
