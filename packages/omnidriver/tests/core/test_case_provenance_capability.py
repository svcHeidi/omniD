"""CaseProvenanceCapability is routed through the adapter exactly like
every Phase 1 capability, with an empty fallback -- which under I1's
precedence means "everything unknown is a required input", the safe
default for a plugin (or plugin version) that declares nothing.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import (
    driver_context
)
from plugins.minimal_plugin import MinimalTestPlugin


def test_minimal_plugin_declares_no_required_inputs(tmp_path: Path) -> None:
    generic = driver_context(
        MinimalTestPlugin(), source="test:minimal-provenance",
    ).capabilities.case_provenance
    assert generic.required_inputs(tmp_path, {}) == ()


def test_minimal_plugin_declares_no_generated_outputs(tmp_path: Path) -> None:
    generic = driver_context(
        MinimalTestPlugin(), source="test:minimal-provenance",
    ).capabilities.case_provenance
    assert generic.generated_output_globs(tmp_path, {}) == ()


def test_a_v1_plugin_with_no_hooks_gets_the_empty_fallback(tmp_path: Path) -> None:
    """A plugin that predates this capability -- v1 or a v2 third-party
    plugin that never implemented it -- must still load and adapt cleanly.
    CaseProvenanceCapability is not a mandatory SolverPlugin member."""
    context = driver_context(MinimalTestPlugin(), source="test")
    assert context.capabilities.case_provenance.required_inputs(tmp_path, {}) == ()
    assert context.capabilities.case_provenance.generated_output_globs(tmp_path, {}) == ()


def test_extra_provenance_paths_is_annotated_as_dependencies():
    """A bare Path can only omit, and omission reads as nothing-to-check.

    That is the gap `RuntimeDependency` was introduced to close, so the
    adapter must not narrow the contract back to `tuple[Path, ...]`.
    """
    import typing
    from omnidriver.core import plugin_capabilities

    hints = typing.get_type_hints(
        plugin_capabilities._RuntimeEvidenceAdapter.extra_provenance_paths,
        include_extras=True,
    )
    assert "RuntimeDependency" in str(hints["return"]), (
        f"annotation is {hints['return']!r}, not a RuntimeDependency tuple"
    )


def test_capability_manifest_does_not_hand_out_a_live_catalog():
    """`get_utility_manifests` was hardened against this; the model
    catalogues were not, and one of them is mutated at import."""
    import pytest
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam import ionic_model_catalog
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    manifest = CardiacFoamPlugin().get_capabilities()
    assert manifest["ionic_models"] is not ionic_model_catalog.IONIC_MODEL_CATALOG
