"""CaseProvenanceCapability assertions specific to the cardiac plugin.

Moved from packages/omnidriver/tests/core/test_case_provenance_capability.py:
the mesh-diagnostic generated-output globs (constant/C, Cx, Cy, Cz,
skewness) and the required-inputs deferral are cardiac plugin knowledge.
The generic-plugin and v1-fallback tests in that file (which already
passed without cardiacfoam installed, since they exercise the empty
fallback CaseProvenanceCapability adapts to when a plugin declares
nothing) stayed in core.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import default_driver_context


def test_cardiac_declares_the_mesh_diagnostic_fields_as_generated_outputs(
    tmp_path: Path,
) -> None:
    """constant/C, Cx, Cy, Cz, skewness are consumed by nothing -- confirmed
    by exhaustive grep across src/ and applications/: zero hits."""
    cardiac = default_driver_context().capabilities.case_provenance
    globs = cardiac.generated_output_globs(tmp_path, {}, "0")
    assert set(globs) == {
        "constant/C",
        "constant/Cx",
        "constant/Cy",
        "constant/Cz",
        "constant/skewness",
    }


def test_cardiac_required_inputs_defers_to_the_safe_default(tmp_path: Path) -> None:
    """Model-dependent per-field required-input resolution is Task 2b's job
    (input enumeration). Returning () here is safe under I1's precedence:
    an unclassified file still defaults to required_input upstream."""
    cardiac = default_driver_context().capabilities.case_provenance
    assert cardiac.required_inputs(tmp_path, {}, "0") == ()
