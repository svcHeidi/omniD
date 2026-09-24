from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from omnidriver.core.capability_manifest import build_capability_manifest
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

    assert context.providers == (plugin,)
    assert context.capabilities.tutorials.catalog() == plugin.get_tutorial_catalog()
    assert context.capabilities.dictionaries.entries() == plugin.get_dict_entries()
    # Corrected 2026-09-22 (Task 10): this used to assert
    # `manifest.manifest() == plugin.get_capabilities()` -- true only because
    # `MinimalTestPlugin.get_capabilities()` happened to return `{}` and
    # `manifest()` was a bare pass-through of whatever the plugin built
    # itself. Core now builds `allowed_commands`/`samplable_fields` itself
    # from the SAME composed reads a plugin's own get_capabilities() used to
    # gather privately, and merges in only what a plugin's own
    # get_capabilities() adds (nothing, for this plugin). Building the
    # expected value the same way core does is the real assertion now: that
    # core no longer needs the plugin to hand back an already-assembled
    # manifest.
    command_authorization = context.capabilities.command_authorization
    case_introspection = context.capabilities.case_introspection
    conventions = context.capabilities.case_runtime_conventions.conventions()
    expected_manifest = build_capability_manifest(
        environment_commands=command_authorization.environment_commands(),
        plugin_commands=(
            command_authorization.solver_commands()
            | command_authorization.auxiliary_commands()
        ),
        utility_manifests=command_authorization.utility_manifests(),
        samplable_fields=case_introspection.samplable_fields({}),
        case_script_commands=(
            frozenset(conventions.case_script_commands)
            | frozenset(conventions.case_entrypoints)
        ),
    )
    expected_manifest.update(plugin.get_capabilities())
    assert context.capabilities.manifest.manifest() == expected_manifest
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
    # A non-cardiac plugin with no build_run_document_config() hook now gets
    # an empty config rather than the cardiac phase vocabulary. Those four
    # phase names are exactly what RunDocument v3 removed from core, where
    # `config` is an open object with no fixed phases (schemas/run-document.json),
    # so handing them to a plugin that never declared them contradicted the
    # schema. Matches legacy_run_document_config_schema, which already handed
    # non-cardiac plugins a fully open schema.
    assert config == {}
    assert diagnostics == ()

    # Existing callers that constructed DriverContext(providers, identity)
    # directly retain the same constructor shape -- now a one-provider stack.
    # This is the same property the pre-composition test proved of `.plugin`:
    # the context does not hide the provider behind the capability adapters.
    reconstructed = DriverContext((plugin,), context.identity)
    assert reconstructed.providers == (plugin,)
    assert reconstructed.capabilities.tutorials.catalog() == plugin.get_tutorial_catalog()
    # 2026-09-24: `plugin_selector` added deliberately -- the `--plugin` value
    # a child process needs to rebuild this context (sweep_run's per-case
    # subprocess). It is optional and trailing, so the positional
    # (providers, identity) constructor above is unchanged, and it holds a
    # string, not a provider, so nothing is hidden behind the adapters.
    assert [item.name for item in fields(reconstructed)] == [
        "providers", "identity", "plugin_selector",
    ]
    assert reconstructed.plugin_selector is None


def test_non_cardiac_plugin_does_not_inherit_cardiac_case_evidence(
    tmp_path: Path,
) -> None:
    """Same rule as :func:`test_report_catalog_is_empty_for_non_cardiac_plugin`,
    applied to case compatibility.

    This test previously asserted the opposite, under the name
    ``test_legacy_plugin_case_evidence_preserves_pre_capability_behavior``: a
    non-cardiac plugin DID claim a case carrying ``electroProperties*``,
    because legacy_case_marker/legacy_case_runnable_without_workflow called
    the cardiac implementation without checking plugin_id -- unlike the
    thirteen sibling fallbacks, which all gate on ``org.cardiacfoam``.

    Preserving that behaviour was never the intent; it was the Plan-1
    fallback's unexamined default, and it meant a third-party plugin was
    silently judged by cardiac filesystem evidence."""
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
    """P2.7: report_catalog.py's former REPORTS tuple was cardiac-specific
    data consumed unconditionally. A non-cardiac v1 plugin must get an empty
    report catalog, not the built-in "Vm field"/"activation map" reports."""
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


def test_config_value_reader_is_none_for_a_plugin_that_declares_nothing() -> None:
    """ConfigValueCapability's fallback is `none`: absence means `None`.

    Added 2026-09-20 (Phase 0 Task 9), alongside the Protocol itself --
    `get_config_value_reader` had no capability at all before this, so
    nothing exercised the adapter's behaviour for a plugin that never
    implements the hook.
    """
    plugin = MinimalTestPlugin()
    context = driver_context(plugin, source="test")

    assert context.capabilities.config_value.reader() is None


def test_config_value_reader_calls_through_to_the_plugin_hook() -> None:
    """When a plugin implements the hook, the adapter returns its callable
    unchanged -- it does not wrap or reinterpret it."""

    def _read(path, key):
        del path, key
        return "sentinel"

    class ReaderPlugin(MinimalTestPlugin):
        def get_config_value_reader(self):
            return _read

    context = driver_context(ReaderPlugin(), source="test")

    reader = context.capabilities.config_value.reader()

    assert reader is _read
    assert reader(Path("unused"), "unused") == "sentinel"


def test_dict_key_scanner_uses_the_fallback_for_a_plugin_that_declares_nothing() -> None:
    """DictKeyScannerCapability's fallback is legacy_dict_key_scanner: absence
    means an empty drift report, not an AttributeError.

    Added 2026-09-22 (Task 11), alongside the Protocol itself --
    `get_dict_key_scanner` had no capability at all before this; strict
    planning imported and called `compatibility.legacy_dict_key_scanner`
    directly at module scope, so nothing exercised the adapter's own
    fallback routing.
    """
    plugin = MinimalTestPlugin()
    context = driver_context(plugin, source="test")

    report = context.capabilities.dict_key_scanner.scan(
        Path("/no/such/source"),
        allowlist_path=Path("/no/such/allowlist.json"),
        entries=(),
    )

    assert report.to_json() == {
        "unmatched_cxx_reads": [],
        "stale_paths": [],
        "unmatched_subdicts": [],
        "unused_allowlist": [],
    }


def test_dict_key_scanner_calls_through_to_the_plugin_hook() -> None:
    """When a plugin implements the hook, the adapter calls the scanner it
    returns instead of falling back to the empty report."""

    calls = []

    def _scan(source_root, *, allowlist_path, entries):
        calls.append((source_root, allowlist_path, entries))
        return "sentinel-report"

    class ScannerPlugin(MinimalTestPlugin):
        def get_dict_key_scanner(self):
            return _scan

    context = driver_context(ScannerPlugin(), source="test")

    report = context.capabilities.dict_key_scanner.scan(
        Path("/src"), allowlist_path=Path("/allow.json"), entries=("e",),
    )

    assert report == "sentinel-report"
    assert calls == [(Path("/src"), Path("/allow.json"), ("e",))]
