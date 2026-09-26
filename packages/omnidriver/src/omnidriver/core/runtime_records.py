"""The files omniD itself writes into a case, declared once, by core (K3).

Spec 2026-09-26-core-generality-design.md §2 (A5): the core half of K3
(openCARP plan Task 15). These names used to be declared only by
``openfoam_case_runtime_conventions()``, so a stack without the OpenFOAM
layer (openCARP) did not know them. Staging a case a run had written then
copied that run's state into the next stage (conformance C11).
``_CaseRuntimeConventionsAdapter.conventions`` merges these into whatever
a stack declares. The OpenFOAM layer's own copies are removed in Task 15.

Corrected 2026-09-26 (R1 fix, finding I3): the module docstring said this
list names "every file core writes into a case" while two names core
actually writes were missing -- the remediation-transaction marker and its
``remediation_transactions``/``remediation_candidates`` directories
(``core.runtime.remediation_transaction``, written through ``step
--apply``/``step_candidate.begin_remediation_transaction``, and persisting
past a rejected repair -- exactly the state A5 and C11 exist to exclude).
Both are now added below, taken from that module's own constants.
``.omnidriver-repair-control`` is not one of these: it is written to
``output_dir.parent``, outside the case (``repair_loop.py``'s
``_control_dir``), so it is never staged into a case in the first place.
"""
from __future__ import annotations

from dataclasses import replace

from .case_transaction import _JOURNAL_RELATIVE_PATH
from .plugin_capabilities import CaseRuntimeConventions
from .runtime.attempt_lease import ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME
from .runtime.postprocess_phase import CASE_RECORD_FILENAME
from .runtime.remediation_transaction import (
    CANDIDATES_DIRECTORY as _REMEDIATION_CANDIDATES_DIRECTORY,
    MARKER_NAME as _REMEDIATION_MARKER_NAME,
    TRANSACTIONS_DIRECTORY as _REMEDIATION_TRANSACTIONS_DIRECTORY,
)
from .runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from .runtime.sweep_manifest import SWEEP_MANIFEST_FILENAME
from .runtime.workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME

#: ``case_transaction``'s per-case journal directory, named by its owner.
_CASE_TRANSACTION_DIRECTORY = _JOURNAL_RELATIVE_PATH.parts[0]

#: Every name below is now read from its owning module's own constant
#: (final review M6, 2026-09-26) rather than restated as a literal here --
#: this closed the gap ``test_core_names_every_file_it_writes_into_a_case``
#: could not see: its docstring claimed the set was "derived from each
#: owning module's own constant" while three of the five core-record names
#: (``workflow_state.json``, ``run_document.json``, ``sweep_manifest.json``,
#: ``case_record.json``, ``workflow_logs``) were still spelled here directly.
#: See ``fresh._OMNIDRIVER_MARKER_NAMES`` for why THAT marker set is a
#: deliberately different three names, not a copy-paste drift of this one.
CORE_RUNTIME_RECORDS = CaseRuntimeConventions(
    generated_directory_names=(
        WORKFLOW_LOGS_DIRNAME, _CASE_TRANSACTION_DIRECTORY,
        _REMEDIATION_TRANSACTIONS_DIRECTORY, _REMEDIATION_CANDIDATES_DIRECTORY,
    ),
    generated_file_names=(
        STATE_FILENAME, RUN_DOCUMENT_FILENAME, SWEEP_MANIFEST_FILENAME, CASE_RECORD_FILENAME,
        ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME, _REMEDIATION_MARKER_NAME,
    ),
    generated_case_markers=(STATE_FILENAME, WORKFLOW_LOGS_DIRNAME, RUN_DOCUMENT_FILENAME),
)


def _union(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    return first + tuple(name for name in second if name not in first)


def with_core_runtime_records(conventions: CaseRuntimeConventions) -> CaseRuntimeConventions:
    """``conventions`` plus core's own records; the plugin's names stay first."""
    return replace(
        conventions,
        generated_directory_names=_union(conventions.generated_directory_names, CORE_RUNTIME_RECORDS.generated_directory_names),
        generated_file_names=_union(conventions.generated_file_names, CORE_RUNTIME_RECORDS.generated_file_names),
        generated_case_markers=_union(conventions.generated_case_markers, CORE_RUNTIME_RECORDS.generated_case_markers),
    )
