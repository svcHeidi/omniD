"""A workflow step's replaceable default arguments."""
from __future__ import annotations

import pytest

from omnidriver.core.runtime.record_execution import _workflow_dag_for_record
from omnidriver.core.tutorial_records import (
    DefaultArgument, TutorialRecord, TutorialRecordError, WorkflowStep,
)

MESH = WorkflowStep(
    step_id="mesh", command=("mesher",),
    default_arguments=(DefaultArgument(key=("-dict",), values=("system/meshDict.3D",)),),
)
GMSH = WorkflowStep(
    step_id="gmsh", command=("gmsh", "-3", "box.geo.template", "-o", "box.msh"),
    default_arguments=(
        DefaultArgument(key=("-setnumber", "lc"), values=("0.1",)),
        DefaultArgument(key=("-setnumber", "nx"), values=("3",)),
    ),
)


def test_a_step_passes_its_default_arguments_when_no_axis_contributes():
    assert MESH.argv() == ("mesher", "-dict", "system/meshDict.3D")
    assert MESH.argv(()) == MESH.argv()


def test_an_axis_passing_the_key_replaces_the_default_and_does_not_duplicate_it():
    argv = MESH.argv(("-dict", "system/meshDict.1D"))
    assert argv == ("mesher", "-dict", "system/meshDict.1D")
    assert argv.count("-dict") == 1


def test_any_value_after_the_key_replaces_the_default_the_record_never_names_it():
    """The record declares the default only."""
    assert MESH.argv(("-dict", "system/agentComposedDict")) == ("mesher", "-dict", "system/agentComposedDict")
    assert GMSH.argv(("-setnumber", "lc", "0.0123")) == (
        "gmsh", "-3", "box.geo.template", "-o", "box.msh",
        "-setnumber", "nx", "3", "-setnumber", "lc", "0.0123",
    )


def test_an_axis_not_passing_the_key_appends_after_the_defaults():
    assert MESH.argv(("-noFunctionObjects",)) == (
        "mesher", "-dict", "system/meshDict.3D", "-noFunctionObjects",
    )


def test_the_key_may_sit_anywhere_in_the_contribution():
    assert MESH.argv(("-noFunctionObjects", "-dict", "system/meshDict.2D")) == (
        "mesher", "-noFunctionObjects", "-dict", "system/meshDict.2D",
    )


def test_a_two_token_key_is_replaced_only_by_both_tokens_together():
    assert GMSH.argv(("-setnumber", "lc", "0.05")) == (
        "gmsh", "-3", "box.geo.template", "-o", "box.msh",
        "-setnumber", "nx", "3",
        "-setnumber", "lc", "0.05",
    )
    # The same flag with another name is a different argument: appended.
    assert GMSH.argv(("-setnumber", "ny", "2")) == (
        "gmsh", "-3", "box.geo.template", "-o", "box.msh",
        "-setnumber", "lc", "0.1", "-setnumber", "nx", "3",
        "-setnumber", "ny", "2",
    )


def test_a_step_with_no_defaults_appends_as_before():
    step = WorkflowStep(step_id="solve", command=("solver",))
    assert step.argv(("-x", "1")) == ("solver", "-x", "1")


def test_an_axis_passing_the_key_twice_is_refused_by_name():
    with pytest.raises(TutorialRecordError) as exc:
        MESH.argv(("-dict", "a", "-dict", "b"))
    message = str(exc.value)
    assert "'mesh'" in message and "['-dict']" in message and "2 times" in message


# -- construction refusals ---------------------------------------------------


def test_a_key_the_command_already_holds_is_refused():
    with pytest.raises(TutorialRecordError, match=r"\['-dict'\]") as exc:
        WorkflowStep(
            step_id="mesh", command=("mesher", "-dict", "fixed"),
            default_arguments=(DefaultArgument(key=("-dict",), values=("x",)),),
        )
    assert "exactly once" in str(exc.value)


def test_two_defaults_with_one_key_are_refused():
    with pytest.raises(TutorialRecordError, match="exactly once"):
        WorkflowStep(
            step_id="mesh", command=("mesher",),
            default_arguments=(
                DefaultArgument(key=("-dict",), values=("a",)),
                DefaultArgument(key=("-dict",), values=("b",)),
            ),
        )


def test_a_key_inside_another_defaults_tokens_is_refused():
    """``-setnumber`` alone and ``-setnumber lc``: an axis passing ``-setnumber lc v`` would name both, so which it replaces is ambiguous."""
    with pytest.raises(TutorialRecordError, match=r"\['-setnumber'\]"):
        WorkflowStep(
            step_id="gmsh", command=("gmsh",),
            default_arguments=(
                DefaultArgument(key=("-setnumber",), values=("lc", "0.1")),
                DefaultArgument(key=("-setnumber", "lc"), values=("0.2",)),
            ),
        )


@pytest.mark.parametrize("key", ["-dict", (), ("",), ("-dict", 3)])
def test_a_malformed_key_is_refused(key):
    with pytest.raises(TutorialRecordError, match="key"):
        DefaultArgument(key=key, values=("x",))


@pytest.mark.parametrize("values", ["x", ("x", 3)])
def test_malformed_values_are_refused(values):
    with pytest.raises(TutorialRecordError, match="values"):
        DefaultArgument(key=("-dict",), values=values)


def test_default_arguments_must_be_default_argument_items():
    with pytest.raises(TutorialRecordError, match="DefaultArgument"):
        WorkflowStep(step_id="mesh", command=("mesher",), default_arguments=(("-dict", "x"),))


# -- the DAG a record runs ---------------------------------------------------

RECORD = TutorialRecord(
    name="toy", native_case_relpath="toy",
    workflow_steps=(MESH, WorkflowStep(step_id="solve", command=("solver",))),
)


def test_the_dag_carries_the_default_when_no_axis_contributes():
    dag = _workflow_dag_for_record(RECORD, workflow_step_ids=("mesh", "solve"), command_arguments={})
    mesh = dag["steps"][0]
    assert (mesh["command"], mesh["args"]) == ("mesher", ["-dict", "system/meshDict.3D"])


def test_the_dag_carries_the_axis_argument_in_place_of_the_default():
    dag = _workflow_dag_for_record(
        RECORD, workflow_step_ids=("mesh", "solve"),
        command_arguments={"mesh": ("-dict", "system/meshDict.1D")},
    )
    assert dag["steps"][0]["args"] == ["-dict", "system/meshDict.1D"]
