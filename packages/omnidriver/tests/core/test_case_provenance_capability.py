"""CaseProvenanceCapability is routed through the adapter exactly like
every Phase 1 capability, with an empty fallback -- which under I1's
precedence means "everything unknown is a required input", the safe
default for a plugin (or plugin version) that declares nothing.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import (
    driver_context,
    generic_openfoam_context,
)
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def test_generic_plugin_declares_no_required_inputs(tmp_path: Path) -> None:
    generic = generic_openfoam_context().capabilities.case_provenance
    assert generic.required_inputs(tmp_path, {}, "0") == ()


def test_generic_plugin_declares_no_generated_outputs(tmp_path: Path) -> None:
    generic = generic_openfoam_context().capabilities.case_provenance
    assert generic.generated_output_globs(tmp_path, {}, "0") == ()


def test_a_v1_plugin_with_no_hooks_gets_the_empty_fallback(tmp_path: Path) -> None:
    """A plugin that predates this capability -- v1 or a v2 third-party
    plugin that never implemented it -- must still load and adapt cleanly.
    CaseProvenanceCapability is not a mandatory SolverPlugin member."""
    context = driver_context(MinimalOpenFOAMPlugin(), source="test")
    assert context.capabilities.case_provenance.required_inputs(tmp_path, {}, "0") == ()
    assert context.capabilities.case_provenance.generated_output_globs(tmp_path, {}, "0") == ()
