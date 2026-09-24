"""Run one tutorial-record case: stage, resolve, and commit (design §4).

The impure counterpart to :mod:`omnidriver.core.tutorial_records`, which is
pure data and pure functions. This module does the filesystem work design
§4 describes end to end for one case:

1. stage the native case into a disposable clone (never writing the native
   tree itself);
2. sort names and run axes against the staged clone (``tutorial_records
   .resolve_case_patches``);
3. drop patches already matching the staged case's current value
   (``tutorial_records.split_unchanged``);
4. commit everything that remains through the existing write channel, in
   ONE ``commit_case_write`` call (design §4 step 7).

``preview_record_case`` performs 1-3 without ever committing -- design §4's
own words: "``describe`` performs steps 1-7 without committing: that is the
preview." ``commit_record_case`` performs all four steps.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from ..case_transaction import commit_case_write
from ..case_write import CaseMutationRequest, CaseWritePlan, CaseWriteRecord
from ..tutorial_records import (
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    patches_to_parameters,
    resolve_case_patches,
    split_unchanged,
)

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


def _native_case_root(record: TutorialRecord, *, cases_root: Path) -> Path:
    native_case_root = Path(cases_root) / record.native_case_relpath
    if not native_case_root.is_dir():
        raise TutorialRecordError(
            f"tutorial record {record.name!r} names a native case path that "
            f"does not exist: {native_case_root}"
        )
    return native_case_root


def _stage(
    record: TutorialRecord, *, cases_root: Path, staged_case_root: Path,
    driver_context: "DriverContext",
) -> None:
    from .sweep_runner import _stage_entry_case

    native_case_root = _native_case_root(record, cases_root=cases_root)
    _stage_entry_case(native_case_root, staged_case_root, driver_context=driver_context)


def _resolve_and_split(
    record: TutorialRecord,
    *,
    study_by_source: Mapping[str, Mapping[str, Any]],
    staged_case_root: Path,
    driver_context: "DriverContext",
) -> tuple[tuple[SourcedPatch, ...], tuple[SourcedPatch, ...], dict[str, tuple[str, ...]]]:
    axis_catalog = driver_context.capabilities.axes.catalog()
    combined, command_arguments = resolve_case_patches(
        record,
        study_by_source=study_by_source,
        axis_catalog=axis_catalog,
        staged_case_root=staged_case_root,
        direct_key_validator=driver_context.capabilities.record_key_validation.validate,
    )
    read_current_value = driver_context.capabilities.config_value.reader()
    values_agree = driver_context.capabilities.case_value_comparison.comparator()
    to_write, unchanged = split_unchanged(
        combined,
        case_root=staged_case_root,
        read_current_value=read_current_value,
        values_agree=values_agree,
    )
    return to_write, unchanged, command_arguments


def preview_record_case(
    record: TutorialRecord,
    *,
    cases_root: Path,
    study_by_source: Mapping[str, Mapping[str, Any]],
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Design §4 steps 1-7 without committing -- ``describe``'s preview.

    Stages the native case into a scratch directory that is discarded when
    this function returns; the real case (if one already exists at this
    entry's staged location) is never touched. Returns a JSON-shaped preview:
    every patch, its status (``"changed"``/``"unchanged"``), its document,
    key, value, and ``validated`` flag -- the round trip design item 6/the
    task's own instruction asks for.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="omnidriver-record-preview-") as scratch:
        staged_case_root = Path(scratch) / "case"
        _stage(
            record, cases_root=cases_root, staged_case_root=staged_case_root,
            driver_context=driver_context,
        )
        to_write, unchanged, command_arguments = _resolve_and_split(
            record, study_by_source=study_by_source,
            staged_case_root=staged_case_root, driver_context=driver_context,
        )
        patches = [
            {
                "document": sourced.patch.document,
                "key_path": list(sourced.patch.key_path),
                "value": sourced.patch.value,
                "value_kind": sourced.patch.value_kind,
                "validated": sourced.patch.validated,
                "source": sourced.source,
                "status": "changed",
            }
            for sourced in to_write
        ] + [
            {
                "document": sourced.patch.document,
                "key_path": list(sourced.patch.key_path),
                "value": sourced.patch.value,
                "value_kind": sourced.patch.value_kind,
                "validated": sourced.patch.validated,
                "source": sourced.source,
                "status": "unchanged",
            }
            for sourced in unchanged
        ]
        return {
            "entry_name": record.name,
            "patches": patches,
            "command_arguments": {
                step: list(args) for step, args in command_arguments.items()
            },
        }


def commit_record_case(
    record: TutorialRecord,
    *,
    cases_root: Path,
    staged_case_root: Path,
    study_by_source: Mapping[str, Mapping[str, Any]],
    driver_context: "DriverContext",
    execution_env: Any | None = None,
    requested_by: str = "tutorial_record",
) -> tuple[CaseWriteRecord | None, dict[str, tuple[str, ...]]]:
    """Design §4 steps 1-8's write half: stage, resolve, and commit ONE case
    in ONE ``commit_case_write`` call (step 7's own words: "everything goes
    in one ``commit_case_write``").

    ``staged_case_root`` persists after this call (unlike
    ``preview_record_case``'s scratch clone) -- it is the sweep's real,
    per-case staging directory, the same one a later workflow-step run reads.

    Returns ``(record_or_none, command_arguments_by_step)``. ``record`` is
    ``None`` when every patch was already unchanged (design §4 step 7:
    "unchanged... not written") -- a legitimate no-op, not a failure, so
    nothing is committed and no transaction is created.
    """
    _stage(
        record, cases_root=cases_root, staged_case_root=staged_case_root,
        driver_context=driver_context,
    )
    to_write, _unchanged, command_arguments = _resolve_and_split(
        record, study_by_source=study_by_source,
        staged_case_root=staged_case_root, driver_context=driver_context,
    )
    if not to_write:
        return None, command_arguments

    identity = getattr(driver_context, "identity", None)
    # `identity.providers[-1]` is the most specific provider in the composed
    # stack -- the same "last is most specific" convention
    # `provider_stack._ComposedProvider.plugin_id` itself uses.
    adapter_id = identity.providers[-1].id if identity is not None else record.name
    parameters = patches_to_parameters(to_write, owner=adapter_id)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=staged_case_root, adapter_id=adapter_id,
        workflow=record.name, source_artifacts=(), parameters=parameters,
        requested_by=requested_by,
    )
    resolved = driver_context.capabilities.case_writer.resolve(
        request, driver_context=driver_context,
    )
    rendered = driver_context.capabilities.case_writer.render(
        resolved, snapshot_root=staged_case_root, driver_context=driver_context,
        execution_env=execution_env,
    )
    stack_identity = identity.capability_digest if identity is not None else "0" * 64
    plan = CaseWritePlan(
        request=request, files=tuple(rendered), preconditions=resolved.preconditions,
        semantic_owner_id=resolved.semantic_owner_id, stack_identity=stack_identity,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expected_effects=resolved.expected_effects,
    )
    record_ = commit_case_write(
        plan, driver_context=driver_context, execution_env=execution_env,
    )
    return record_, command_arguments
