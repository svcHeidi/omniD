"""Declaration surface consumed by provenance, telemetry and observables; nothing here reads these yet."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context

from plugins.minimal_plugin import MinimalTestPlugin


def test_generic_declares_no_solve_steps() -> None:
    evidence = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert evidence.solve_step_commands() == frozenset()


def test_a_command_with_no_declared_globs_returns_empty() -> None:
    """The CONTRAST is the assertion, not the empty tuple."""
    plugin = MinimalTestPlugin(telemetry_globs={"run-test-case": ("log.*",)})
    evidence = driver_context(
        plugin, source="test:telemetry",
    ).capabilities.runtime_evidence

    assert evidence.telemetry_source_globs("run-test-case") == ("log.*",)
    assert evidence.telemetry_source_globs("blockMesh") == ()


def test_extra_provenance_paths_default_to_empty(tmp_path: Path) -> None:
    generic = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert generic.extra_provenance_paths(tmp_path) == ()


def test_an_unknown_artifact_format_has_no_reader() -> None:
    """Kept deliberately weak, and labelled as such."""
    evidence = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert evidence.artifact_value_reader("not_a_real_format") is None


def test_generic_plugin_provides_no_artifact_readers() -> None:
    evidence = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert evidence.artifact_value_reader("openfoam_log") is None
