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
from .runtime.remediation_transaction import (
    CANDIDATES_DIRECTORY as _REMEDIATION_CANDIDATES_DIRECTORY,
    MARKER_NAME as _REMEDIATION_MARKER_NAME,
    TRANSACTIONS_DIRECTORY as _REMEDIATION_TRANSACTIONS_DIRECTORY,
)

#: ``case_transaction``'s per-case journal directory, named by its owner.
_CASE_TRANSACTION_DIRECTORY = _JOURNAL_RELATIVE_PATH.parts[0]

CORE_RUNTIME_RECORDS = CaseRuntimeConventions(
    generated_directory_names=(
        "workflow_logs", _CASE_TRANSACTION_DIRECTORY,
        _REMEDIATION_TRANSACTIONS_DIRECTORY, _REMEDIATION_CANDIDATES_DIRECTORY,
    ),
    generated_file_names=(
        "workflow_state.json", "run_document.json", "sweep_manifest.json", "case_record.json",
        ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME, _REMEDIATION_MARKER_NAME,
    ),
    generated_case_markers=("workflow_state.json", "workflow_logs", "run_document.json"),
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
