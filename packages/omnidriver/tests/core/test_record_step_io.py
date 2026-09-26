"""K4: a record step names the case files it reads and writes."""
from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from omnidriver.core.runtime.record_execution import (
    _workflow_dag_for_record, record_artifact_id, record_case_spec, record_step_artifacts,
)
from omnidriver.core.tutorial_records import (
    PLAIN_FILE_FORMAT, ProducedPath, TutorialRecord, TutorialRecordError, WorkflowStep,
)

RECORD = TutorialRecord(
    name="io",
    native_case_relpath="io",
    allowed_axes=frozenset(),
    workflow_steps=(
        WorkflowStep(step_id="mesh", command=("m",), produces=("a.pts", "a.elem")),
        WorkflowStep(step_id="solve", command=("s",), consumes=("in.par",), produces=("out/v.igb",)),
    ),
)


def test_artifacts_come_from_produces():
    artifacts = record_step_artifacts(RECORD, ("mesh", "solve"))
    assert [(a.artifact_id, a.path_pattern, a.produced_by) for a in artifacts] == [
        ("record.mesh.0", "a.pts", "mesh"),
        ("record.mesh.1", "a.elem", "mesh"),
        ("record.solve.0", "out/v.igb", "solve"),
    ]


def test_unselected_steps_declare_nothing():
    assert [a.artifact_id for a in record_step_artifacts(RECORD, ("solve",))] == ["record.solve.0"]


def test_dag_carries_ids_and_consumed_paths():
    dag = _workflow_dag_for_record(RECORD, workflow_step_ids=("mesh", "solve"), command_arguments={})
    by_id = {step["id"]: step for step in dag["steps"]}
    assert by_id["mesh"]["produces"] == [record_artifact_id("mesh", 0), record_artifact_id("mesh", 1)]
    assert by_id["solve"]["consumes"] == ["in.par"]


def test_spec_declares_expected_artifacts(tmp_path: Path):
    spec = record_case_spec(RECORD, case_id="io", staged_case_root=tmp_path,
                            workflow_step_ids=("mesh", "solve"), command_arguments={})
    assert [a.artifact_id for a in spec.metadata["expected_artifacts"]] == [
        "record.mesh.0", "record.mesh.1", "record.solve.0",
    ]


@pytest.mark.parametrize("bad", ["/abs/path", "../escape"])
def test_paths_must_be_case_relative(bad):
    with pytest.raises(TutorialRecordError, match="case-relative"):
        WorkflowStep(step_id="x", command=("c",), produces=(bad,))


@pytest.mark.parametrize("field", ["produces", "consumes"])
def test_a_bare_string_is_refused_not_exploded_into_characters(field):
    """M1: tuple("solved.marker") would be thirteen one-character paths."""
    with pytest.raises(TutorialRecordError, match=field):
        WorkflowStep(step_id="x", command=("c",), **{field: "solved.marker"})


@pytest.mark.parametrize("field", ["produces", "consumes"])
@pytest.mark.parametrize("bad", ["", ".", "./", "out/{x}.dat", "a}b"])
def test_empty_root_and_brace_paths_are_refused(field, bad):
    """M1: "." names the case root itself; a brace is later str.format-ed."""
    with pytest.raises(TutorialRecordError, match=field):
        WorkflowStep(step_id="x", command=("c",), **{field: (bad,)})


@pytest.mark.parametrize("field", ["produces", "consumes"])
def test_a_non_string_item_is_a_record_error(field):
    with pytest.raises(TutorialRecordError, match=field):
        WorkflowStep(step_id="x", command=("c",), **{field: (Path("a.txt"),)})


def test_a_refusal_names_the_step_once():
    with pytest.raises(TutorialRecordError) as excinfo:
        WorkflowStep(step_id="solve", command=("c",), consumes=("/abs",))
    assert str(excinfo.value).count("workflow step 'solve'") == 1


def test_a_step_keeps_its_utility_manifest_produces_beside_its_own():
    """I6: a step's declared ``produces`` is unioned with its command's
    utility-manifest ``produces``, never a replacement. Replacing left the
    manifest ids unclaimed, and the unclaimed branch credited them to the
    last solver step -- which then failed for a file it never writes."""
    from omnidriver.core.runtime.workflow import normalize_workflow_dag

    dag, _diagnostics = normalize_workflow_dag(
        {"steps": [
            {"id": "solve", "command": "s"},
            {"id": "post", "command": "u", "depends_on": ["solve"], "produces": ["record.post.0"]},
        ]},
        utility_produces={"u": ("u.metrics", "u.series")},
        driver_context=None,
    )
    by_id = {step["id"]: step for step in dag["steps"]}
    assert by_id["post"]["produces"] == ["record.post.0", "u.metrics", "u.series"]
    assert by_id["solve"]["produces"] == []


def test_a_step_without_its_own_produces_still_takes_the_manifest():
    from omnidriver.core.runtime.workflow import normalize_workflow_dag

    dag, _diagnostics = normalize_workflow_dag(
        {"steps": [{"id": "post", "command": "u"}]},
        utility_produces={"u": ("u.metrics",)}, driver_context=None,
    )
    assert dag["steps"][0]["produces"] == ["u.metrics"]


# ---------------------------------------------------------------------------
# Task 1 (results-as-quantities, topic B): ProducedPath -- a produces entry
# names its own format, read only through WorkflowStep.produced_format.
# ---------------------------------------------------------------------------


def test_a_plain_produces_path_is_an_unread_file():
    step = WorkflowStep(step_id="solve", command=("s",), produces=("out/v.igb",))
    assert step.produces == ("out/v.igb",)
    assert step.produced_format("out/v.igb") == PLAIN_FILE_FORMAT == "file"


def test_a_produced_path_is_its_path_and_names_its_format():
    step = WorkflowStep(step_id="solve", command=("s",),
                        produces=("out/v.igb", ProducedPath("out/lat.dat", format="toy_lat")))
    # every existing reader of `produces` still sees plain paths
    assert step.produces == ("out/v.igb", "out/lat.dat")
    assert all(isinstance(path, str) for path in step.produces)
    assert json.dumps(list(step.produces)) == '["out/v.igb", "out/lat.dat"]'
    assert step.produced_format("out/lat.dat") == "toy_lat"
    # the format survives the copies core and tests make
    assert copy.deepcopy(step).produced_format("out/lat.dat") == "toy_lat"
    assert dataclasses.replace(step, command=("t",)).produced_format("out/lat.dat") == "toy_lat"


def test_record_artifacts_carry_the_declared_format():
    record = TutorialRecord(
        name="fmt", native_case_relpath="fmt", allowed_axes=frozenset(),
        workflow_steps=(WorkflowStep(step_id="solve", command=("s",),
                                     produces=("out/v.igb", ProducedPath("out/lat.dat", format="toy_lat"))),),
    )
    assert [(a.path_pattern, a.format) for a in record_step_artifacts(record, ("solve",))] == [
        ("out/v.igb", "file"), ("out/lat.dat", "toy_lat"),
    ]


@pytest.mark.parametrize("bad", ["", " toy", "file"])
def test_a_format_must_be_named_and_not_the_plain_meaning(bad):
    with pytest.raises(TutorialRecordError, match="format"):
        ProducedPath("out/lat.dat", format=bad)


@pytest.mark.parametrize("second", [ProducedPath("out/lat.dat", format="other"), "out/lat.dat"])
def test_a_formatted_path_is_declared_once(second):
    with pytest.raises(TutorialRecordError, match="more than once"):
        WorkflowStep(step_id="solve", command=("s",),
                     produces=(ProducedPath("out/lat.dat", format="toy_lat"), second))


def test_a_format_on_consumes_is_refused():
    with pytest.raises(TutorialRecordError, match="belongs on the step that produces"):
        WorkflowStep(step_id="solve", command=("s",), consumes=(ProducedPath("in.dat", format="toy"),))


def test_the_format_of_a_path_the_step_does_not_produce_is_refused_by_name():
    step = WorkflowStep(step_id="solve", command=("s",), produces=("out/v.igb",))
    with pytest.raises(TutorialRecordError, match="'out/lat.dat'"):
        step.produced_format("out/lat.dat")
