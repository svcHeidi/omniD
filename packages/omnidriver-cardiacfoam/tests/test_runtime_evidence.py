"""RuntimeEvidence declarations specific to the cardiac plugin.

Moved from packages/omnidriver/tests/core/test_runtime_evidence.py: these
name the cardiac solver command (``cardiacFoam``), its post-processing
utility (``bathBidomainInterfaceMetrics``), the ``Allrun``-redirected
``log.*`` telemetry glob, and the cardiacFoam binary as a required runtime
dependency -- all cardiac plugin knowledge. The generic-plugin tests in that
file (which already passed without cardiacfoam installed) stayed in core,
along with two cases (``test_a_command_with_no_declared_globs_returns_empty``
and ``test_an_unknown_artifact_format_has_no_reader``) that were left
failing there deliberately: they are trivially true under any plugin and
``artifact_value_reader`` has no real implementation yet, so moving them
would not have been a meaningful split.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import default_driver_context


def test_cardiac_declares_its_solver_as_a_solve_step() -> None:
    evidence = default_driver_context().capabilities.runtime_evidence
    assert "cardiacFoam" in evidence.solve_step_commands()


def test_a_post_processing_utility_is_not_a_solve_step() -> None:
    """bathBidomainInterfaceMetrics is authorized to run but does not solve;
    Phase 4 must not expect solver telemetry from it."""
    evidence = default_driver_context().capabilities.runtime_evidence
    assert "bathBidomainInterfaceMetrics" not in evidence.solve_step_commands()


def test_allrun_declares_a_log_glob_so_redirected_output_is_findable() -> None:
    """OpenFOAM's runApplication redirects solver output to log.<app>, so an
    Allrun step produces no parseable driver-captured stdout."""
    evidence = default_driver_context().capabilities.runtime_evidence
    globs = evidence.telemetry_source_globs("Allrun")
    assert any("log." in glob for glob in globs)


def test_cardiac_extra_provenance_paths_declares_the_solver_as_a_dependency(
    tmp_path: Path,
) -> None:
    """End-to-end through the adapter: the whole reason extra_provenance_paths
    was replaced with a typed RuntimeDependency form is so the cardiacFoam
    binary itself -- never named by an Allrun-driven step's command -- is
    still declared as something Phase 2 must fingerprint."""
    from omnidriver.core.plugin_capabilities import RuntimeDependency

    evidence = default_driver_context().capabilities.runtime_evidence
    dependencies = evidence.extra_provenance_paths(tmp_path)
    assert dependencies
    assert all(isinstance(dependency, RuntimeDependency) for dependency in dependencies)
    by_name = {dependency.name: dependency for dependency in dependencies}
    assert "cardiacFoam" in by_name
    assert by_name["cardiacFoam"].required is True
