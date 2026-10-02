"""Which on-disk files a workflow run consumes, as seen through cardiacFoam's CaseProvenanceCapability."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:provenance_inputs")
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs


def _paths(components, *, kind: str | None = None) -> set[str]:
    return {c.path for c in components if kind is None or c.kind == kind}


def _write_control_dict(case_root: Path, *, start_from: str, start_time: str = "0") -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "controlDict").write_text(
        f"startFrom       {start_from};\nstartTime       {start_time};\n"
        "endTime         1;\ndeltaT          0.01;\n"
    )


def test_system_and_constant_are_required_and_diagnostic_outputs_are_excluded(tmp_path: Path) -> None:
    """constant/C and constant/skewness are mesh-diagnostic byproducts nothing reads."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "electroProperties").write_text("solver monodomain;\n")
    (tmp_path / "constant" / "C").write_bytes(b"mesh-diagnostic-byproduct")
    (tmp_path / "constant" / "skewness").write_bytes(b"mesh-diagnostic-byproduct")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=_CTX,
    )
    included = _paths(components, kind="case_file")

    assert "system/controlDict" in included
    assert "constant/electroProperties" in included
    assert "constant/C" not in included
    assert "constant/skewness" not in included
