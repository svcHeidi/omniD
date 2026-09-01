"""Samplable fields and case-model resolution are plugin knowledge."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import generic_openfoam_context


def _cardiac_case(root: Path) -> Path:
    (root / "constant").mkdir(parents=True)
    (root / "constant" / "electroProperties").write_text(
        "myocardiumSolver monodomainSolver;\n"
    )
    return root


def test_generic_plugin_exposes_no_cardiac_fields(tmp_path: Path) -> None:
    introspection = generic_openfoam_context().capabilities.case_introspection
    resolved = introspection.resolve_case_models(_cardiac_case(tmp_path))
    fields = introspection.samplable_fields(resolved)
    flat = [name for names in fields.values() for name in names]
    assert "Vm" not in flat
    assert "phiE" not in flat
