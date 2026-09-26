"""Core declares its own run records, and record staging drops a record's
step outputs (spec 2026-09-26-core-generality-design.md §2, A5)."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.record_execution import record_generated_relpaths
from omnidriver.core.runtime.sweep_runner import _stage_entry_case
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, with_core_runtime_records
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from plugins.minimal_plugin import MinimalTestPlugin


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_core_names_every_file_it_writes_into_a_case():
    assert set(CORE_RUNTIME_RECORDS.generated_file_names) == {
        "workflow_state.json", "run_document.json", "sweep_manifest.json", "case_record.json",
        ".omnidriver-attempt.lock", ".omnidriver-attempt.lock.guard",
    }
    assert set(CORE_RUNTIME_RECORDS.generated_directory_names) == {"workflow_logs", ".omnidriver"}


def test_a_stack_that_declares_nothing_still_knows_cores_records():
    ctx = driver_context(MinimalTestPlugin(), source="test")
    assert ctx.capabilities.case_runtime_conventions.conventions() == CORE_RUNTIME_RECORDS


def test_merging_keeps_the_plugins_names_first_and_adds_cores_once():
    merged = with_core_runtime_records(
        CaseRuntimeConventions(generated_file_names=("run_document.json", "log.x")),
    )
    assert merged.generated_file_names[:2] == ("run_document.json", "log.x")
    assert merged.generated_file_names.count("run_document.json") == 1
    assert set(CORE_RUNTIME_RECORDS.generated_file_names) <= set(merged.generated_file_names)


def test_a_records_generated_paths_are_what_it_produces_and_does_not_consume():
    record = TutorialRecord(
        name="r", native_case_relpath="r", allowed_axes=frozenset(),
        workflow_steps=(
            WorkflowStep(step_id="mesh", command=("m",), produces=("mesh.pts", "out")),
            WorkflowStep(step_id="fix", command=("f",), consumes=("in_place.par",), produces=("in_place.par",)),
        ),
    )
    assert record_generated_relpaths(record) == frozenset({"mesh.pts", "out"})


def test_staging_drops_excluded_paths_at_any_depth_and_cores_records(tmp_path):
    source = tmp_path / "source"
    for relpath in ("out/a.dat", "keep/b.txt", "keep/gen.txt", "workflow_state.json", "workflow_logs/s.log", "input.par"):
        (source / relpath).parent.mkdir(parents=True, exist_ok=True)
        (source / relpath).write_text(relpath)
    staged = tmp_path / "staged"
    _stage_entry_case(
        source, staged, driver_context=driver_context(MinimalTestPlugin(), source="test"),
        excluded_relpaths=frozenset({"out", "keep/gen.txt"}),
    )
    assert _tree(staged) == ["input.par", "keep", "keep/b.txt"]
