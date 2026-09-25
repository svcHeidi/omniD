"""K4: a record step names the case files it reads and writes."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.record_execution import (
    _workflow_dag_for_record, record_artifact_id, record_case_spec, record_step_artifacts,
)
from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError, WorkflowStep

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
