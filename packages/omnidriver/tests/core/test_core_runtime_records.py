"""Core declares its own run records, and record staging drops a record's
step outputs."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.case_transaction import _JOURNAL_RELATIVE_PATH
from omnidriver.core.plugin_interface import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.attempt_lease import (
    ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME,
)
from omnidriver.core.runtime.case_records import CASE_RECORD_FILENAME
from omnidriver.core.runtime.record_execution import record_generated_relpaths
from omnidriver.core.runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from omnidriver.core.runtime.sweep_manifest import SWEEP_MANIFEST_FILENAME
from omnidriver.core.runtime.sweep_runner import _stage_entry_case
from omnidriver.core.runtime.workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, case_runtime_conventions, with_core_runtime_records
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from plugins.toy import ToyProvider


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_core_names_every_file_it_writes_into_a_case():
    """Every expected name is imported from its owning module's constant, so a rename there is what this test catches."""
    assert set(CORE_RUNTIME_RECORDS.generated_file_names) == {
        STATE_FILENAME, RUN_DOCUMENT_FILENAME, SWEEP_MANIFEST_FILENAME, CASE_RECORD_FILENAME,
        ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME,
    }
    assert set(CORE_RUNTIME_RECORDS.generated_directory_names) == {
        WORKFLOW_LOGS_DIRNAME, _JOURNAL_RELATIVE_PATH.parts[0],
    }


def test_a_stack_that_declares_nothing_still_knows_cores_records():
    ctx = driver_context(ToyProvider(), source="test")
    assert case_runtime_conventions(ctx) == CORE_RUNTIME_RECORDS


def test_merging_keeps_the_plugins_names_first_and_adds_cores_once():
    merged = with_core_runtime_records(
        CaseRuntimeConventions(generated_file_names=(RUN_DOCUMENT_FILENAME, "log.x")),
    )
    assert merged.generated_file_names[:2] == (RUN_DOCUMENT_FILENAME, "log.x")
    assert merged.generated_file_names.count(RUN_DOCUMENT_FILENAME) == 1
    assert set(CORE_RUNTIME_RECORDS.generated_file_names) <= set(merged.generated_file_names)


def test_a_records_generated_paths_are_what_it_produces_and_does_not_consume():
    record = TutorialRecord(
        name="r", native_case_relpath="r",
        workflow_steps=(
            WorkflowStep(step_id="mesh", command=("m",), produces=("mesh.pts", "out")),
            WorkflowStep(step_id="fix", command=("f",), consumes=("in_place.par",), produces=("in_place.par",)),
        ),
    )
    assert record_generated_relpaths(record) == frozenset({"mesh.pts", "out"})


def test_an_intermediate_a_later_step_consumes_is_still_excluded():
    """A path one step produces and a later step consumes (e.g. a mesh a solve step reads) is an intermediate, not an authored input; a restage must still exclude it."""
    record = TutorialRecord(
        name="r", native_case_relpath="r",
        workflow_steps=(
            WorkflowStep(step_id="mesh", command=("m",), produces=("slab.pts", "slab.elem")),
            WorkflowStep(
                step_id="solve", command=("s",),
                consumes=("nversion.par", "slab.pts", "slab.elem"),
                produces=("out",),
            ),
        ),
    )
    assert record_generated_relpaths(record) == frozenset({"slab.pts", "slab.elem", "out"})


def test_staging_drops_excluded_paths_at_any_depth_and_cores_records(tmp_path):
    source = tmp_path / "source"
    for relpath in (
        "out/a.dat", "keep/b.txt", "keep/gen.txt", STATE_FILENAME,
        f"{WORKFLOW_LOGS_DIRNAME}/s.log", "input.par",
    ):
        (source / relpath).parent.mkdir(parents=True, exist_ok=True)
        (source / relpath).write_text(relpath)
    staged = tmp_path / "staged"
    _stage_entry_case(
        source, staged, driver_context=driver_context(ToyProvider(), source="test"),
        excluded_relpaths=frozenset({"out", "keep/gen.txt"}),
    )
    assert _tree(staged) == ["input.par", "keep", "keep/b.txt"]
