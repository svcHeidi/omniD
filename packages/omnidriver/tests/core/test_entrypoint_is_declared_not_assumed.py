"""Every site that needs the case entrypoint must ask the plugin for it."""
from __future__ import annotations

import pytest

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import (
    entrypoint_command,
    entrypoint_relpaths,
    is_environment_role,
)
from omnidriver.core.runtime.generic_case import _workflow_dag_for

import plugins.minimal_plugin as minimal_plugin


def _context(entrypoint):
    return driver_context(
        minimal_plugin.MinimalTestPlugin(entrypoint=entrypoint),
        source="test:entrypoint",
    )


def test_no_context_has_no_environment_entrypoint_default() -> None:
    assert entrypoint_relpaths(None) == ()
    with pytest.raises(ValueError, match="entrypoint"):
        entrypoint_command(None)


def test_a_plugin_declaring_no_entrypoint_has_no_entrypoint() -> None:
    assert entrypoint_relpaths(_context(None)) == ()


def test_a_declared_entrypoint_wins_over_the_default() -> None:
    assert entrypoint_relpaths(_context("RunCase.sh")) == ("RunCase.sh",)
    assert entrypoint_command(_context("RunCase.sh")) == "RunCase.sh"


def test_the_generic_dag_invokes_the_declared_entrypoint() -> None:
    """The literal here meant the one generated step ran the wrong script."""
    dag = _workflow_dag_for(
        solver_command=None,
        pre_solve_commands=(),
        driver_context=_context("RunCase.sh"),
    )
    assert [step["command"] for step in dag["steps"]] == ["RunCase.sh"]

    with pytest.raises(ValueError, match="entrypoint"):
        _workflow_dag_for(solver_command=None, pre_solve_commands=())


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


@pytest.mark.parametrize(
    "role,environment_owned",
    [
        ("openfoam.control_dict", True),
        ("openfoam.entrypoint", True),
        ("x-fenics.mesh_file", True),
        ("x-dealii.parameters", True),
        ("plugin.configuration", False),
        ("case.documentation", False),
        ("case.regression_test", False),
        ("no_namespace", False),
    ],
)
def test_environment_ownership_is_not_an_openfoam_prefix_test(role, environment_owned) -> None:
    """A foreign environment's files are the environment's, not core's."""
    assert is_environment_role(role) is environment_owned


# Step S6 (2026-09-28) deleted `tutorial_contracts.describe_tutorial_contract`,
# `is_environment_role`'s only production call site (the
# `core_required_files`/`solver_required_files` split it decided). The test
# that exercised that call site (not just the pure helper above),
# `test_an_escape_role_is_reported_as_the_environment_s_file`, went with it --
# there is no longer a call site to exercise, only the helper the
# parametrized test above already covers directly.
