"""The files core itself writes into a case, declared once here so any stack
(including one without the OpenFOAM layer) knows them when staging a case:
:func:`case_runtime_conventions` merges them into what the stack declares.
"""
from __future__ import annotations

from dataclasses import replace

from .case_transaction import COMMIT_MARKER_FILENAME
from .plugin_interface import CaseRuntimeConventions
from .runtime.attempt_lease import ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME
from .runtime.case_records import CASE_RECORD_FILENAME
from .runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from .runtime.sweep_manifest import SWEEP_MANIFEST_FILENAME
from .runtime.workflow_orchestrator import STATE_FILENAME, WORKFLOW_LOGS_DIRNAME

#: Every name is read from its owning module's own constant, never restated
#: as a literal, so this set cannot drift from what those modules actually
#: write. Distinct from ``fresh._OMNIDRIVER_MARKER_NAMES``, a smaller,
#: deliberately different set -- not a copy-paste of this one.
CORE_RUNTIME_RECORDS = CaseRuntimeConventions(
    generated_directory_names=(WORKFLOW_LOGS_DIRNAME,),
    generated_file_names=(
        STATE_FILENAME, RUN_DOCUMENT_FILENAME, SWEEP_MANIFEST_FILENAME, CASE_RECORD_FILENAME,
        ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME, COMMIT_MARKER_FILENAME,
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


def case_runtime_conventions(driver_context) -> CaseRuntimeConventions:
    """The stack's declared generated paths, plus core's own run records,
    which a stack declaring none still needs: staging a case a run wrote
    must not carry core's state into the next stage."""
    declared = driver_context.stack.call("get_case_runtime_conventions")
    if not isinstance(declared, CaseRuntimeConventions):
        raise TypeError(
            f"get_case_runtime_conventions() must return CaseRuntimeConventions, got {declared!r}"
        )
    return with_core_runtime_records(declared)
