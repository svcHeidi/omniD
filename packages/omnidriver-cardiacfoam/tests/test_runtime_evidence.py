"""RuntimeEvidence declarations specific to the cardiac plugin: its solver command, a post-processing
utility, the ``Allrun``-redirected ``log.*`` telemetry glob, and the cardiacFoam binary as a dependency."""

from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

# These declarations are cardiacFoam's own, so name the plugin: the ambient default
# has no single answer once a second adapter is installed.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:runtime_evidence")


def test_cardiac_declares_its_solver_as_a_solve_step() -> None:
    evidence = _CTX.capabilities.runtime_evidence
    assert "cardiacFoam" in evidence.solve_step_commands()


def test_a_post_processing_utility_is_not_a_solve_step() -> None:
    """It is authorized to run but does not solve, so no solver telemetry is expected from it."""
    evidence = _CTX.capabilities.runtime_evidence
    assert "bathBidomainInterfaceMetrics" not in evidence.solve_step_commands()


def test_allrun_declares_a_log_glob_so_redirected_output_is_findable() -> None:
    """OpenFOAM's runApplication redirects solver output to log.<app>, leaving no parseable stdout."""
    evidence = _CTX.capabilities.runtime_evidence
    globs = evidence.telemetry_source_globs("Allrun")
    assert any("log." in glob for glob in globs)


def test_cardiac_extra_provenance_paths_declares_the_solver_as_a_dependency(
    tmp_path: Path,
) -> None:
    """The binary is never named by an Allrun-driven step's command, yet must still be fingerprinted."""
    from omnidriver.core.plugin_capabilities import RuntimeDependency

    evidence = _CTX.capabilities.runtime_evidence
    dependencies = evidence.extra_provenance_paths(tmp_path)
    assert dependencies
    assert all(isinstance(dependency, RuntimeDependency) for dependency in dependencies)
    by_name = {dependency.name: dependency for dependency in dependencies}
    assert "cardiacFoam" in by_name
    assert by_name["cardiacFoam"].required is True
