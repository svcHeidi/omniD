"""Samplable fields and case-model resolution are plugin knowledge."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from plugins.toy import ToyProvider


def _cardiac_case(root: Path) -> Path:
    (root / "constant").mkdir(parents=True)
    (root / "constant" / "electroProperties").write_text(
        "myocardiumSolver monodomainSolver;\n"
    )
    return root


def test_generic_plugin_exposes_no_cardiac_fields(tmp_path: Path) -> None:
    stack = driver_context(ToyProvider(), source="test:neutral-introspection").stack
    resolved = stack.call("resolve_case_models", _cardiac_case(tmp_path))
    fields = stack.call("get_samplable_fields", resolved)
    flat = [name for names in fields.values() for name in names]
    assert "Vm" not in flat
    assert "phiE" not in flat
