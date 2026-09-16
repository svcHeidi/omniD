"""Runtime-evidence declarations exposed through plugin capabilities."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context

from plugins.minimal_plugin import MinimalTestPlugin


def test_generic_declares_no_solve_steps() -> None:
    evidence = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert evidence.solve_step_commands() == frozenset()


def test_a_command_with_no_declared_globs_returns_empty() -> None:
    """The CONTRAST is the assertion, not the empty tuple.

    Asked of a plugin that declares nothing, this returned () for every input
    -- including one it does declare, because there is no such input. That is
    vacuous: it holds however broken the lookup is. Declaring globs for one
    command and asking for another is the claim worth pinning.
    """
    plugin = MinimalTestPlugin(telemetry_globs={"run-test-case": ("log.*",)})
    evidence = driver_context(
        plugin, source="test:telemetry",
    ).capabilities.runtime_evidence

    assert evidence.telemetry_source_globs("run-test-case") == ("log.*",)
    assert evidence.telemetry_source_globs("blockMesh") == ()


def test_extra_provenance_paths_default_to_empty(tmp_path: Path) -> None:
    generic = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert generic.extra_provenance_paths(tmp_path) == ()


def test_generic_plugin_provides_no_artifact_readers() -> None:
    evidence = driver_context(MinimalTestPlugin(), source="test:evidence").capabilities.runtime_evidence
    assert evidence.artifact_value_reader("openfoam_log") is None
