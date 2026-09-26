"""Core declares its own run records, and record staging drops a record's
step outputs (spec 2026-09-26-core-generality-design.md §2, A5)."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.case_transaction import _JOURNAL_RELATIVE_PATH
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.attempt_lease import (
    ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME,
)
from omnidriver.core.runtime.postprocess_phase import CASE_RECORD_FILENAME
from omnidriver.core.runtime.record_execution import record_generated_relpaths
from omnidriver.core.runtime.remediation_transaction import (
    CANDIDATES_DIRECTORY as REMEDIATION_CANDIDATES_DIRECTORY,
    MARKER_NAME as REMEDIATION_MARKER_NAME,
    TRANSACTIONS_DIRECTORY as REMEDIATION_TRANSACTIONS_DIRECTORY,
)
from omnidriver.core.runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from omnidriver.core.runtime.sweep_manifest import SWEEP_MANIFEST_FILENAME
from omnidriver.core.runtime.sweep_runner import _stage_entry_case
from omnidriver.core.runtime.workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME
from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, with_core_runtime_records
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from plugins.minimal_plugin import MinimalTestPlugin


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_core_names_every_file_it_writes_into_a_case():
    """Corrected 2026-09-26 (R1 fix, finding I3): two names were missing --
    the remediation-transaction marker and its directories
    (``runtime.remediation_transaction``). The expected set is now derived
    from each owning module's own constant, not restated as a literal, so a
    name missing from ``CORE_RUNTIME_RECORDS`` still fails this even if it
    is also missing here.

    Corrected again 2026-09-26 (final review M6): "derived from each
    owning module's own constant" was true for two of the seven names and
    restated as a literal for the rest (``workflow_state.json``,
    ``run_document.json``, ``sweep_manifest.json``, ``case_record.json``,
    ``workflow_logs``) -- both here and in ``CORE_RUNTIME_RECORDS`` itself.
    Every name below is now imported from its owner
    (``workflow_orchestrator.STATE_FILENAME``/``WORKFLOW_LOGS_DIRNAME``,
    ``run_document_exec.RUN_DOCUMENT_FILENAME``,
    ``sweep_manifest.SWEEP_MANIFEST_FILENAME``,
    ``postprocess_phase.CASE_RECORD_FILENAME``), so a rename at the owner
    is what this test would actually catch."""
    assert set(CORE_RUNTIME_RECORDS.generated_file_names) == {
        STATE_FILENAME, RUN_DOCUMENT_FILENAME, SWEEP_MANIFEST_FILENAME, CASE_RECORD_FILENAME,
        ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME, REMEDIATION_MARKER_NAME,
    }
    assert set(CORE_RUNTIME_RECORDS.generated_directory_names) == {
        WORKFLOW_LOGS_DIRNAME, _JOURNAL_RELATIVE_PATH.parts[0],
        REMEDIATION_TRANSACTIONS_DIRECTORY, REMEDIATION_CANDIDATES_DIRECTORY,
    }


def test_a_stack_that_declares_nothing_still_knows_cores_records():
    ctx = driver_context(MinimalTestPlugin(), source="test")
    assert ctx.capabilities.case_runtime_conventions.conventions() == CORE_RUNTIME_RECORDS


def test_merging_keeps_the_plugins_names_first_and_adds_cores_once():
    merged = with_core_runtime_records(
        CaseRuntimeConventions(generated_file_names=(RUN_DOCUMENT_FILENAME, "log.x")),
    )
    assert merged.generated_file_names[:2] == (RUN_DOCUMENT_FILENAME, "log.x")
    assert merged.generated_file_names.count(RUN_DOCUMENT_FILENAME) == 1
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


def test_an_intermediate_a_later_step_consumes_is_still_excluded():
    """R1 fix, finding I2: a path one step produces and a LATER step
    consumes is an intermediate (a mesh a solve step reads), not an
    authored input updated in place -- it must still be excluded, or a
    restage carries the earlier run's mesh forward (the reviewer's
    pipeline evidence: openCARP's mesh step produces slab.pts/slab.elem,
    and an honestly-declared solve step consumes them)."""
    record = TutorialRecord(
        name="r", native_case_relpath="r", allowed_axes=frozenset(),
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
        source, staged, driver_context=driver_context(MinimalTestPlugin(), source="test"),
        excluded_relpaths=frozenset({"out", "keep/gen.txt"}),
    )
    assert _tree(staged) == ["input.par", "keep", "keep/b.txt"]
