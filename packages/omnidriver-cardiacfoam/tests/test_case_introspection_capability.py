"""Samplable fields and case-model resolution the cardiac plugin exposes.

Moved from packages/omnidriver/tests/core/test_case_introspection_capability.py:
these assertions name cardiac-specific fields (``Vm``, ``activationTime``),
the cardiac dictionary layout (``constant/electroProperties``), and the
deprecated tuple-returning shim that hardcodes the cardiac default context
internally -- all cardiac plugin knowledge. The generic-plugin test in that
file (which already passed without cardiacfoam installed) stayed in core.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import default_driver_context


def _cardiac_case(root: Path) -> Path:
    (root / "constant").mkdir(parents=True)
    (root / "constant" / "electroProperties").write_text(
        "myocardiumSolver monodomainSolver;\n"
    )
    return root


def test_cardiac_plugin_exposes_its_fixed_fields(tmp_path: Path) -> None:
    introspection = default_driver_context().capabilities.case_introspection
    resolved = introspection.resolve_case_models(_cardiac_case(tmp_path))
    assert resolved["solver"] == "monodomainSolver"
    electro = introspection.samplable_fields(resolved)["electro"]
    assert "Vm" in electro
    assert "activationTime" in electro


def test_missing_case_file_resolves_to_none_without_raising(tmp_path: Path) -> None:
    introspection = default_driver_context().capabilities.case_introspection
    resolved = introspection.resolve_case_models(tmp_path)
    assert resolved == {"solver": None, "ionic_model": None, "active_tension": None}


def test_no_active_tension_means_no_solid_region(tmp_path: Path) -> None:
    """A spatial EP solver alone must not imply a mechanics region."""
    introspection = default_driver_context().capabilities.case_introspection
    resolved = introspection.resolve_case_models(_cardiac_case(tmp_path))
    assert introspection.samplable_fields(resolved)["solid"] == ()


def test_deprecated_tuple_shim_still_returns_three_values(tmp_path: Path) -> None:
    from omnidriver.core.capability_manifest import resolve_case_models

    assert resolve_case_models("/nonexistent/case") == (None, None, None)
    assert resolve_case_models(_cardiac_case(tmp_path))[0] == "monodomainSolver"
