"""Every site that needs the case entrypoint must ask the plugin for it.

Phase 1 gave `registry.py` a declared `openfoam.entrypoint` role and used it
for case detection. Three other sites kept the literal `"Allrun"`, so a plugin
naming its entrypoint anything else got:

* `workflow.py`'s `producer_commands` missing its own run step, which credits
  unclaimed artifacts to no step at all, and
* `generic_case.py`'s one-step DAG invoking a script the case does not contain.

Both were invisible because every shipped plugin does call it `Allrun` --
two constants agreeing by coincidence, which is the same shape as the
`output_dir_name` defect. So these tests assert the CONTRAST: a plugin
declaring a different entrypoint must move every one of those answers.
"""
from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import (
    DEFAULT_ENTRYPOINT_RELPATHS,
    entrypoint_command,
    entrypoint_relpaths,
    is_environment_role,
)
from omnidriver.core.runtime.generic_case import _workflow_dag_for

import plugins.minimal_plugin as minimal_plugin


def _context(entrypoint):
    return driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint=entrypoint),
        source="test:entrypoint",
    )


def test_no_context_falls_back_to_the_documented_default() -> None:
    assert entrypoint_relpaths(None) == DEFAULT_ENTRYPOINT_RELPATHS
    assert entrypoint_command(None) == "Allrun"


def test_a_plugin_declaring_no_entrypoint_gets_the_default() -> None:
    """Declaring nothing is not the same as declaring something odd."""
    assert entrypoint_relpaths(_context(None)) == DEFAULT_ENTRYPOINT_RELPATHS


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

    default = _workflow_dag_for(solver_command=None, pre_solve_commands=())
    assert [step["command"] for step in default["steps"]] == ["Allrun"]


def test_the_declared_entrypoint_can_produce_artifacts() -> None:
    """`producer_commands` must contain the plugin's entrypoint, not "Allrun".

    Asserted through the public builder rather than the private set: an
    unclaimed artifact is credited to the last producer step, so if the
    entrypoint is not recognised as a producer there is no step to credit and
    the artifact stays unclaimed.
    """
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
    """A foreign environment's files are the environment's, not core's.

    `role.startswith("openfoam.")` gave the right answer for every shipped
    role and the wrong one for every escape role, which is exactly the case
    the escape tier was added to allow.
    """
    assert is_environment_role(role) is environment_owned


def test_an_escape_role_is_reported_as_the_environment_s_file(tmp_path) -> None:
    """The call site, not just the helper.

    Testing `is_environment_role` in isolation passes whether or not
    `tutorial_contracts` actually calls it -- reverting that call site to
    `role.startswith("openfoam.")` left the parametrized test above entirely
    green. This exercises the split itself: a foreign environment's required
    file must be reported under `solver_required_files`, not
    `core_required_files`.
    """
    from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
    from omnidriver.core.runtime.generic_case import make_spec
    from omnidriver.core.tutorial_contracts import describe_tutorial_contract

    case_root = tmp_path / "myCase"
    case_root.mkdir()
    (case_root / "domain.xdmf").write_text("mesh")
    (case_root / "plugin.cfg").write_text("cfg")

    class _ForeignEnvironmentPlugin(minimal_plugin.MinimalOpenFOAMPlugin):
        def get_profile(self):
            rules = (
                CaseFileRule(
                    path="domain.xdmf", kind="dictionary",
                    role="x-fenics.mesh_file", required="always",
                ),
                CaseFileRule(
                    path="plugin.cfg", kind="dictionary",
                    role="plugin.configuration", required="always",
                ),
            )
            return PluginProfile(
                path=tmp_path / "plugin.yaml",
                plugin_id=self.plugin_id,
                api_version=self.plugin_api_version,
                case_files=rules,
                cxx_mapping=None,
                payload={
                    "schema_version": 1,
                    "plugin": {"id": self.plugin_id,
                               "api_version": self.plugin_api_version},
                    "case_profile": {"dictionaries": []},
                },
            )

    context = driver_context(_ForeignEnvironmentPlugin(), source="test:foreign")
    spec = make_spec(tutorials_root=tmp_path, case_dir_name="myCase")
    contract = describe_tutorial_contract(
        spec, resolution="test", driver_context=context,
    )

    assert "domain.xdmf" in contract["solver_required_files"], (
        "a foreign environment's required file was filed as core's own"
    )
    assert "plugin.cfg" in contract["core_required_files"]
    assert "domain.xdmf" not in contract["core_required_files"]
