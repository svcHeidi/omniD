"""The files core itself writes into a case, declared once here so any stack
(including one without the OpenFOAM layer) knows them when staging a case --
``_CaseRuntimeConventionsAdapter.conventions`` merges this into whatever the
plugin stack declares.
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

#: Every name is read from its owning module's own constant, never restated
#: as a literal, so this set cannot drift from what those modules actually
#: write. Distinct from ``fresh._OMNIDRIVER_MARKER_NAMES``, a smaller,
#: deliberately different set -- not a copy-paste of this one.
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
