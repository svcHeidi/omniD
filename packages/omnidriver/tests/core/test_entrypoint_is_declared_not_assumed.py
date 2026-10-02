"""Every site that needs the case entrypoint must ask the plugin for it."""
from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import entrypoint_relpaths

import plugins.toy as toy


def _context(entrypoint):
    return driver_context(
        toy.ToyProvider(entrypoint=entrypoint),
        source="test:entrypoint",
    )


def test_no_context_has_no_environment_entrypoint_default() -> None:
    assert entrypoint_relpaths(None) == ()


def test_a_plugin_declaring_no_entrypoint_has_no_entrypoint() -> None:
    assert entrypoint_relpaths(_context(None)) == ()


def test_a_declared_entrypoint_wins_over_the_default() -> None:
    assert entrypoint_relpaths(_context("RunCase.sh")) == ("RunCase.sh",)


def test_the_declared_entrypoint_can_produce_artifacts() -> None:
    """`producer_commands` must contain the plugin's entrypoint, not "Allrun"."""
    from omnidriver.core.runtime.models import DataArtifact
    from omnidriver.core.runtime.workflow import normalize_workflow_dag

    artifact = DataArtifact(
        artifact_id="some_output",
        path_pattern="out.csv",
        format="json_summary",
    )

    def _produces(entrypoint: str, context) -> tuple[str, ...]:
        dag, _diagnostics = normalize_workflow_dag(
            {"steps": [{"id": "run", "command": entrypoint, "cwd": "."}]},
            expected_artifacts=(artifact,),
            driver_context=context,
        )
        assert dag is not None
        step = next(s for s in dag["steps"] if s["id"] == "run")
        return tuple(step["produces"])

    assert _produces("RunCase.sh", _context("RunCase.sh")) == ("some_output",), (
        "the declared entrypoint was not treated as a producer, so the "
        "unclaimed artifact was credited to no step at all"
    )
    # Contrast: the same step name is NOT a producer when the plugin declares
    # a different entrypoint, which is what proves the answer is being read
    # from the declaration rather than matched against a literal.
    assert _produces("RunCase.sh", _context("Allrun")) == ()
