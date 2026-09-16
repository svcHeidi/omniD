from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from omnidriver.core.plugin_capabilities import (
    ArtifactPredictionRequest,
    CaseCompatibilityRequest,
    ConfigurationValidationRequest,
    RunDocumentConfigurationRequest,
    RunSemanticValidationRequest,
)
from omnidriver.core.plugin_interface import DriverContext, driver_context
from omnidriver.core.runtime.models import TutorialSpec
from plugins.minimal_plugin import MinimalTestPlugin


def _spec(tmp_path: Path) -> TutorialSpec:
    return TutorialSpec(
        name="minimal",
        case_root=tmp_path,
        setup_root=tmp_path,
        output_dir=tmp_path / "postProcessing",
        build_cases=lambda: [],
        apply_case=lambda *_args: None,
        metadata={"generic_case": True},
    )


def test_context_exposes_focused_adapters_without_replacing_public_plugin(
    tmp_path: Path,
) -> None:
    plugin = MinimalTestPlugin()
    context = driver_context(plugin, source="test")
    spec = _spec(tmp_path)

    assert context.plugin is plugin
    assert context.capabilities.tutorials.catalog() == plugin.get_tutorial_catalog()
    assert context.capabilities.dictionaries.entries() == plugin.get_dict_entries()
    assert context.capabilities.manifest.manifest() == plugin.get_capabilities()
    assert context.capabilities.configuration_validator.validate(
        ConfigurationValidationRequest(spec),
    ) == ()
    assert context.capabilities.run_semantic_validator.validate(
        RunSemanticValidationRequest({}),
    ) == ()
    assert context.capabilities.artifacts.predict(
        ArtifactPredictionRequest(tmp_path, spec),
    ) == ()
    config, diagnostics = context.capabilities.run_document_configuration.build(
        RunDocumentConfigurationRequest(spec),
    )
    # The optional builder has a neutral empty result; the required plugin
    # schema decides whether that result is valid.
    assert config == {}
    assert diagnostics == ()

    # Existing callers that constructed DriverContext(plugin, identity)
    # directly retain the same constructor shape.
    reconstructed = DriverContext(plugin, context.identity)
    assert reconstructed.plugin is plugin
    assert reconstructed.capabilities.tutorials.catalog() == plugin.get_tutorial_catalog()
    assert [item.name for item in fields(reconstructed)] == ["plugin", "identity"]


def test_non_cardiac_plugin_does_not_inherit_cardiac_case_evidence(
    tmp_path: Path,
) -> None:
    """Case-compatibility defaults contain no solver-specific evidence."""
    plugin = MinimalTestPlugin()
    context = driver_context(plugin, source="test")
    case_root = tmp_path / "case"
    for relative in (
        "constant/electroProperties.variant",
        "constant/physicsProperties",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
    ):
        path = case_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")

    request = CaseCompatibilityRequest(case_root)
    assert not context.capabilities.case_compatibility.has_case_marker(request)
    assert not context.capabilities.case_compatibility.is_runnable_without_workflow(
        request
    )


def test_report_catalog_is_empty_for_non_cardiac_plugin() -> None:
    """A plugin without the optional hook has an empty report catalog."""
    plugin = MinimalTestPlugin()
    context = driver_context(plugin, source="test")

    reports = context.capabilities.report_catalog.reports()

    assert reports == ()
    assert not any("Vm field" in r.title for r in reports)
    assert not any("activation map" in r.title.lower() for r in reports)


def test_capability_adapter_preserves_plugin_exceptions(tmp_path: Path) -> None:
    class ThrowingPlugin(MinimalTestPlugin):
        def validate_configuration(self, spec):
            del spec
            raise RuntimeError("same failure")

    context = driver_context(ThrowingPlugin(), source="test")
    with pytest.raises(RuntimeError, match="same failure"):
        context.capabilities.configuration_validator.validate(
            ConfigurationValidationRequest(_spec(tmp_path)),
        )
