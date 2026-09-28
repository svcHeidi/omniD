"""CaseProvenanceCapability assertions specific to the cardiac plugin."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:case_provenance_capability")


def test_cardiac_declares_the_mesh_diagnostic_fields_as_generated_outputs(
    tmp_path: Path,
) -> None:
    """Nothing in the native src/ or applications/ reads constant/C, Cx, Cy, Cz or skewness."""
    cardiac = _CTX.capabilities.case_provenance
    globs = cardiac.generated_output_globs(tmp_path, {})
    assert set(globs) == {
        "constant/C",
        "constant/Cx",
        "constant/Cy",
        "constant/Cz",
        "constant/skewness",
    }


def test_cardiac_required_inputs_defers_to_the_safe_default(tmp_path: Path) -> None:
    """Returning () is safe: an unclassified file still defaults to required_input upstream."""
    cardiac = _CTX.capabilities.case_provenance
    assert cardiac.required_inputs(tmp_path, {}) == ()
