"""Declaration surface consumed by Phase 2 (provenance), Phase 4 (telemetry),
and Phase 5 (observables). Nothing in Phase 1 reads these yet -- they exist so
those phases need not reopen the plugin contract mid-flight."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context

from plugins.minimal_plugin import MinimalOpenFOAMPlugin


def test_generic_declares_no_solve_steps() -> None:
    evidence = generic_openfoam_context().capabilities.runtime_evidence
    assert evidence.solve_step_commands() == frozenset()


def test_a_command_with_no_declared_globs_returns_empty() -> None:
    """The CONTRAST is the assertion, not the empty tuple.

    Asked of a plugin that declares nothing, this returned () for every input
    -- including one it does declare, because there is no such input. That is
    vacuous: it holds however broken the lookup is. Declaring globs for one
    command and asking for another is the claim worth pinning.
    """
    plugin = MinimalOpenFOAMPlugin(telemetry_globs={"Allrun": ("log.*",)})
    evidence = driver_context(
        plugin, source="test:telemetry",
    ).capabilities.runtime_evidence

    assert evidence.telemetry_source_globs("Allrun") == ("log.*",)
    assert evidence.telemetry_source_globs("blockMesh") == ()


def test_extra_provenance_paths_default_to_empty(tmp_path: Path) -> None:
    generic = generic_openfoam_context().capabilities.runtime_evidence
    assert generic.extra_provenance_paths(tmp_path) == ()


def test_an_unknown_artifact_format_has_no_reader() -> None:
    """Kept deliberately weak, and labelled as such.

    ``get_artifact_value_reader`` returns None for EVERY format in every
    shipped plugin today -- runtime_evidence.py records that readers arrive in
    Phase 5 -- so this cannot yet assert a contrast the way its sibling above
    does. It is a placeholder guarding the adapter's plumbing, not the
    behaviour. When Phase 5 lands a real reader, rewrite this to assert the
    known format resolves and an unrelated string does not.
    """
    evidence = generic_openfoam_context().capabilities.runtime_evidence
    assert evidence.artifact_value_reader("not_a_real_format") is None


def test_generic_plugin_provides_no_artifact_readers() -> None:
    evidence = generic_openfoam_context().capabilities.runtime_evidence
    assert evidence.artifact_value_reader("openfoam_log") is None
