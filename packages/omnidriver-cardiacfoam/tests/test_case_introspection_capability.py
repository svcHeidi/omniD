"""Samplable fields and case-model resolution the cardiac plugin exposes."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:case_introspection_capability")


def _cardiac_case(root: Path) -> Path:
    (root / "constant").mkdir(parents=True)
    (root / "constant" / "electroProperties").write_text(
        "myocardiumSolver monodomainSolver;\n"
    )
    return root


def test_cardiac_plugin_exposes_its_fixed_fields(tmp_path: Path) -> None:
    resolved = _CTX.stack.call("resolve_case_models", _cardiac_case(tmp_path))
    assert resolved["solver"] == "monodomainSolver"
    electro = _CTX.stack.call("get_samplable_fields", resolved)["electro"]
    assert "Vm" in electro
    assert "activationTime" in electro


def test_missing_case_file_resolves_to_none_without_raising(tmp_path: Path) -> None:
    resolved = _CTX.stack.call("resolve_case_models", tmp_path)
    assert resolved == {"solver": None, "ionic_model": None, "active_tension": None}


def test_no_active_tension_means_no_solid_region(tmp_path: Path) -> None:
    resolved = _CTX.stack.call("resolve_case_models", _cardiac_case(tmp_path))
    assert _CTX.stack.call("get_samplable_fields", resolved)["solid"] == ()
