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

import contextlib
import datetime
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence

from ..case_transaction import commit_case_write
from ..case_write import CaseMutationRequest, CaseWritePlan, CaseWriteRecord
from ..sweep.sweep_derivation_catalog import NAMING_OUTPUT_KEYS
from .models import DataArtifact
from ..tutorial_records import (
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    _strictly_equal,
    patches_to_parameters,
    resolve_case_patches,
    resolve_variant_selector,
    split_unchanged,
)

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


@dataclass(frozen=True)
class RecordCommitResult:
    """The outcome of :func:`commit_record_case` (review finding M5).

    Before this existed, "every patch was unchanged" and "something was
    committed" were told apart only by a bare ``CaseWriteRecord | None`` --
    a caller seeing ``None`` learned that nothing was written, but not that
    this was because every patch already matched, nor what those unchanged
    patches even were. ``status`` says which case this is, explicitly;
    ``unchanged`` carries the patches themselves either way (design §4 step
    7 already reports them in ``preview_record_case``'s preview -- this is
    the same information on the commit path).
    """

    write_record: CaseWriteRecord | None
    unchanged: tuple[SourcedPatch, ...]
    command_arguments: dict[str, tuple[str, ...]]
    #: Item 4/item 2: the ordered step ids this case's workflow actually
    #: runs -- the record's own steps, or one selected variant's, per
    #: `_resolve_workflow_step_ids`. The caller that runs the workflow (sweep
    #: dispatch) needs this alongside `command_arguments` to build the DAG.
    workflow_step_ids: tuple[str, ...]

    @property
    def status(self) -> str:
        return "committed" if self.write_record is not None else "unchanged"


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


def _reserved_study_names(record: TutorialRecord) -> frozenset[str]:
    """Reserved study names that name neither a document key nor an axis,
    and must never reach ``sort_study_name`` (item 3, item 4): the two sweep
    naming-derivation outputs (``NAMING_OUTPUT_KEYS`` -- pure sweep-machinery
    bookkeeping, never case content) and THIS RECORD'S OWN
    ``variant_selector`` name, if it declares one (a variant choice, never a
    patch). Explicit, matching CLAUDE.md's "no fallback" standard -- nothing
    here is inferred from shape, and core reserves no selector name of its
    own (item 4's vocabulary fix: ``MESH_SELECTOR_NAME`` was deleted; each
    record declares its own).
    """
    if record.variant_selector is None:
        return NAMING_OUTPUT_KEYS
    return NAMING_OUTPUT_KEYS | frozenset({record.variant_selector})


def _extract_reserved_names(
    study_by_source: Mapping[str, Mapping[str, Any]],
    *,
    reserved_names: frozenset[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Strip every reserved name out of every source, refusing a value that
    conflicts across sources by name (item 3 + item 4's selector).

    Returns ``(stripped_study_by_source, reserved_values)`` -- the latter
    maps each reserved name actually present in the study to its one agreed
    value.

    Conflict is checked with strict same-type equality (``_strictly_equal``,
    shared with ``tutorial_records.combine_patches``'s own patch-conflict
    check), not plain ``==`` -- ``1`` and ``True`` compare equal under
    Python's numeric tower but come from two callers who each meant a
    different value, and a plain ``!=`` would silently let the second (a
    real conflict) through as "agreement".
    """
    stripped: dict[str, dict[str, Any]] = {}
    reserved_values: dict[str, Any] = {}
    reserved_source: dict[str, str] = {}
    for source, values in study_by_source.items():
        remaining = dict(values)
        for name in reserved_names:
            if name not in remaining:
                continue
            candidate = remaining.pop(name)
            if name in reserved_values and not _strictly_equal(reserved_values[name], candidate):
                raise TutorialRecordError(
                    f"{name!r} is set to different values by "
                    f"{reserved_source[name]!r} ({reserved_values[name]!r}) "
                    f"and {source!r} ({candidate!r})"
                )
            reserved_values[name] = candidate
            reserved_source[name] = source
        stripped[source] = remaining
    return stripped, reserved_values


def _resolve_workflow_step_ids(
    record: TutorialRecord, reserved_values: Mapping[str, Any],
) -> tuple[str, ...]:
    """Item 4: the record's own steps, or one selected variant's steps.

    A record that declares ``workflow_variants`` REQUIRES the study to name
    its own ``variant_selector`` -- no silent default among declared
    variants. A record with no variants at all requires the study NOT to
    name one (refused via ``resolve_variant_selector`` itself: "declares no
    workflow_variants").
    """
    selector_name = record.variant_selector
    selector_value = reserved_values.get(selector_name) if selector_name is not None else None
    if record.workflow_variants:
        if selector_value is None:
            raise TutorialRecordError(
                f"tutorial record {record.name!r} declares workflow_variants "
                f"{sorted(record.workflow_variants)}; the study must supply "
                f"{selector_name!r} to select one"
            )
        return resolve_variant_selector(record, selector_value)
    if selector_value is not None:
        return resolve_variant_selector(record, selector_value)  # raises: no variants
    return record.step_ids()


def _resolve_and_split(
    record: TutorialRecord,
    *,
    study_by_source: Mapping[str, Mapping[str, Any]],
    staged_case_root: Path,
    driver_context: "DriverContext",
) -> tuple[
    tuple[SourcedPatch, ...], tuple[SourcedPatch, ...],
    dict[str, tuple[str, ...]], tuple[str, ...],
]:
    # M1: neither of these two capabilities has a compatibility fallback any
    # more (`:fallback: none`, matching ConfigValueCapability/
    # CaseWriterCapability) -- a stack that composes no record-key validator
    # or no case-value comparator cannot run a tutorial-record case at all,
    # and must say so BY NAME rather than silently accepting every key
    # unchecked or reporting every no-op patch as "changed" and writing it
    # (review finding M4/E8).
    validator = driver_context.capabilities.record_key_validation.validator()
    if validator is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no record-key validator (get_record_key_validator); a "
            "record case's keys cannot be checked against any catalog"
        )
    comparator = driver_context.capabilities.case_value_comparison.comparator()
    if comparator is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no case-value comparator (get_case_value_comparator); "
            "whether a patch is unchanged cannot be determined"
        )
    read_current_value = driver_context.capabilities.config_value.reader()
    if read_current_value is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no config-value reader (get_config_value_reader); "
            "whether a patch is unchanged cannot be determined"
        )
    study_by_source, reserved_values = _extract_reserved_names(
        study_by_source, reserved_names=_reserved_study_names(record),
    )
    workflow_step_ids = _resolve_workflow_step_ids(record, reserved_values)
    # No fallback for axes either, but an absent axis catalog IS a neutral
    # state here (design §3: "Core... ships no solver axes" -- most stacks
    # provide none at all), not a refusal: `sort_study_name` already refuses
    # any bare study name by name when no adapter provides that axis.
    axis_catalog = driver_context.capabilities.axes.catalog() or {}
    combined, command_arguments = resolve_case_patches(
        record,
        study_by_source=study_by_source,
        axis_catalog=axis_catalog,
        staged_case_root=staged_case_root,
        direct_key_validator=validator,
    )
    to_write, unchanged = split_unchanged(
        combined,
        case_root=staged_case_root,
        read_current_value=read_current_value,
        values_agree=comparator,
    )
    return to_write, unchanged, command_arguments, workflow_step_ids


def _serialize_sourced_patch(sourced: SourcedPatch, *, status: str) -> dict[str, Any]:
    """One patch's JSON shape, shared by ``preview_record_case``'s preview
    and (M5-of-2a) the sweep manifest/summary's own per-case
    ``unchanged_patches`` -- one definition of "what a patch looks like on
    the wire", not two independently maintained ones."""
    return {
        "document": sourced.patch.document,
        "key_path": list(sourced.patch.key_path),
        "value": sourced.patch.value,
        "value_kind": sourced.patch.value_kind,
        "validated": sourced.validated,
        "source": sourced.source,
        "status": status,
    }


def _seed_snapshot_root(
    snapshot_root: Path, *, case_root: Path, documents: frozenset[str],
) -> None:
    """Copy each target document from the real (staged) case into
    ``snapshot_root`` before a renderer ever sees it -- P2 fix,
    docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md,
    "Owner decisions" dated 2026-09-25.

    ``render_case_files``'s own contract (``plugin_interface.py``) already
    promises this: "writes nothing outside ``snapshot_root``, an isolated
    copy core provides." Before this fix, core handed a renderer an EMPTY
    directory instead -- true for the OpenFOAM renderer only by accident
    (``openfoam.case_rendering`` reads ``resolved.request.case_root``
    directly and re-seeds its own copy from there, never trusting core's
    ``snapshot_root`` to already hold anything), and silently wrong for any
    renderer that takes the contract at its word (the ``tests/plugins
    /e2e_record_plugin.py`` fixture: it reads ``snapshot_root/<document>``,
    finds nothing, and treats an EXISTING multi-key document as brand new --
    a patch that then holds only the just-touched keys, discarding every
    sibling key the moment it is committed). A document the case does not
    yet hold is left unseeded: the renderer legitimately sees it as new,
    the only situation where ``exists_before=False`` is true, and
    :func:`omnidriver.core.case_transaction._check_render_exists_before`
    (the P2 fix's other half) now refuses a renderer that gets this wrong
    in either direction, before a single byte is written.
    """
    for document in sorted(documents):
        source = Path(case_root) / document
        if not source.is_file():
            continue
        destination = snapshot_root / document
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


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
        to_write, unchanged, command_arguments, workflow_step_ids = _resolve_and_split(
            record, study_by_source=study_by_source,
            staged_case_root=staged_case_root, driver_context=driver_context,
        )
        patches = [
            _serialize_sourced_patch(sourced, status="changed") for sourced in to_write
        ] + [
            _serialize_sourced_patch(sourced, status="unchanged") for sourced in unchanged
        ]
        return {
            "entry_name": record.name,
            "patches": patches,
            "command_arguments": {
                step: list(args) for step, args in command_arguments.items()
            },
            "workflow_step_ids": list(workflow_step_ids),
        }


@contextlib.contextmanager
def _refusal_as_record_error(
    record: TutorialRecord, documents: frozenset[str], action: str,
) -> Iterator[None]:
    """A ``ValueError`` the plugin's case writer raises while resolving or
    rendering -- its contract's refusal type, e.g. a renderer refusing a
    value the key validator could not see was wrong -- becomes a
    ``TutorialRecordError`` naming the record and the document(s), with the
    original message and the original exception chained (wave-2 review I2).

    Without this, ``plan --strict`` reported a validator refusal as JSON but a
    renderer refusal as a traceback on stderr with empty stdout: the shape of
    a refusal depended on which layer refused. A non-``ValueError`` is a
    defect, not a refusal, and still propagates as itself."""
    try:
        yield
    except TutorialRecordError:
        raise
    except ValueError as exc:
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: {action} {', '.join(sorted(documents))} "
            f"was refused by the case writer ({type(exc).__name__}): {exc}"
        ) from exc


def commit_record_case(
    record: TutorialRecord,
    *,
    cases_root: Path,
    staged_case_root: Path,
    study_by_source: Mapping[str, Mapping[str, Any]],
    driver_context: "DriverContext",
    execution_env: Any | None = None,
    requested_by: str = "tutorial_record",
) -> RecordCommitResult:
    """Design §4 steps 1-8's write half: stage, resolve, and commit ONE case
    in ONE ``commit_case_write`` call (step 7's own words: "everything goes
    in one ``commit_case_write``").

    ``staged_case_root`` persists after this call (unlike
    ``preview_record_case``'s scratch clone) -- it is the sweep's real,
    per-case staging directory, the same one a later workflow-step run reads.

    Returns a :class:`RecordCommitResult` (review finding M5). Its
    ``write_record`` is ``None`` when every patch was already unchanged
    (design §4 step 7: "unchanged... not written") -- a legitimate no-op, not
    a failure, so nothing is committed and no transaction is created -- but
    ``result.status``/``result.unchanged`` say so explicitly rather than
    leaving a bare ``None`` for the caller to interpret.
    """
    import tempfile

    _stage(
        record, cases_root=cases_root, staged_case_root=staged_case_root,
        driver_context=driver_context,
    )
    to_write, unchanged, command_arguments, workflow_step_ids = _resolve_and_split(
        record, study_by_source=study_by_source,
        staged_case_root=staged_case_root, driver_context=driver_context,
    )
    if not to_write:
        return RecordCommitResult(
            write_record=None, unchanged=unchanged, command_arguments=command_arguments,
            workflow_step_ids=workflow_step_ids,
        )

    # `DriverContext.identity` has no default -- it is always present, never
    # a defensive `getattr(..., None)` away from missing (minor m1: that
    # fallback, and the "0" * 64 digest placeholder it justified, were dead
    # code). `identity.resolutions["case_writer"]` names whichever provider
    # in the composed stack actually answers `case_writer` -- correct even
    # when that is not the most specific provider, unlike the
    # `providers[-1].id` guess this replaces.
    identity = driver_context.identity
    adapter_id = identity.resolutions["case_writer"]
    parameters = patches_to_parameters(to_write, owner=adapter_id)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=staged_case_root, adapter_id=adapter_id,
        workflow=record.name, source_artifacts=(), parameters=parameters,
        requested_by=requested_by,
    )
    documents = frozenset(parameter.document for parameter in parameters)
    with _refusal_as_record_error(record, documents, "resolving"):
        resolved = driver_context.capabilities.case_writer.resolve(
            request, driver_context=driver_context,
        )
    # `snapshot_root` MUST be a directory distinct from `request.case_root`
    # (module docstring of `openfoam.case_rendering`: "the real case is read
    # only to seed [a] copy" under `snapshot_root` -- never the same
    # directory). Passing `staged_case_root` for both used to make every
    # real (non-test-double) renderer's seeding copy a no-op `shutil.copy2`
    # of a file onto itself, raising `shutil.SameFileError` the first time
    # this path ever ran against the real OpenFOAM dictionary renderer
    # (found running `restitutionCurves`'s pilot sweep end to end, step 4b:
    # every existing test of this function used a toy case_writer test
    # double whose own renderer does not perform that seeding copy, so nothing
    # caught it earlier). A fresh scratch directory, discarded once `rendered`
    # is captured, matches `cardiacfoam.overrides.commit_case_overrides`'s own
    # established pattern exactly.
    #
    # P2 fix (2026-09-25): that scratch directory is now SEEDED before the
    # renderer ever sees it -- `_seed_snapshot_root` copies each target
    # document's CURRENT bytes in from the staged case, so a renderer that
    # reads `snapshot_root/<document>` (per `render_case_files`'s own "an
    # isolated copy core provides" contract) finds the real prior content,
    # not an always-empty directory. The OpenFOAM renderer does not depend
    # on this (it reads `resolved.request.case_root` directly and seeds its
    # own copy from there); this closes the gap for every renderer that
    # takes the framework's own documented contract at its word instead.
    with tempfile.TemporaryDirectory(prefix="omnidriver-record-render-") as scratch:
        snapshot_root = Path(scratch)
        _seed_snapshot_root(
            snapshot_root, case_root=staged_case_root, documents=documents,
        )
        with _refusal_as_record_error(record, documents, "rendering"):
            rendered = driver_context.capabilities.case_writer.render(
                resolved, snapshot_root=snapshot_root, driver_context=driver_context,
                execution_env=execution_env,
            )
    plan = CaseWritePlan(
        request=request, files=tuple(rendered), preconditions=resolved.preconditions,
        semantic_owner_id=resolved.semantic_owner_id, stack_identity=identity.capability_digest,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        expected_effects=resolved.expected_effects,
    )
    record_ = commit_case_write(
        plan, driver_context=driver_context, execution_env=execution_env,
    )
    return RecordCommitResult(
        write_record=record_, unchanged=unchanged, command_arguments=command_arguments,
        workflow_step_ids=workflow_step_ids,
    )


# ---------------------------------------------------------------------------
# Item 2: running a committed record case's workflow through the SAME
# workflow-DAG shape and the SAME planning/run machinery a factory tutorial
# uses -- no second runner.
# ---------------------------------------------------------------------------


def _workflow_dag_for_record(
    record: TutorialRecord,
    *,
    workflow_step_ids: tuple[str, ...],
    command_arguments: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    """The record's selected steps, in the exact ``{"steps": [...]}`` shape
    ``generic_case._workflow_dag_for`` already produces for factory
    tutorials: one entry per step, ``command``/``args`` split, chained by
    ``depends_on`` in declaration order (design's own worked example runs a
    meshing step then a solve step, one after another -- core knows neither
    tool by name).

    An axis's command arguments for a step (``AxisResult.command_arguments``,
    already merged and conflict-checked by ``resolve_case_patches``, M6) are
    appended after the step's own declared ``command`` tail.
    """
    steps_by_id = {step.step_id: step for step in record.workflow_steps}
    dag_steps: list[dict[str, Any]] = []
    depends_on: list[str] = []
    for step_id in workflow_step_ids:
        step = steps_by_id[step_id]
        argv = list(step.command) + list(command_arguments.get(step_id, ()))
        step_entry: dict[str, Any] = {
            "id": step_id,
            "command": argv[0],
            "args": argv[1:],
            "depends_on": list(depends_on),
        }
        record_step = steps_by_id[step_id]
        step_entry["produces"] = [record_artifact_id(step_id, i) for i in range(len(record_step.produces))]
        step_entry["consumes"] = list(record_step.consumes)
        dag_steps.append(step_entry)
        depends_on = [step_id]
    return {"steps": dag_steps}


def record_artifact_id(step_id: str, index: int) -> str:
    """The artifact id a record step's ``index``-th ``produces`` path gets."""
    return f"record.{step_id}.{index}"


def record_step_artifacts(record: TutorialRecord, workflow_step_ids: Sequence[str]) -> tuple[DataArtifact, ...]:
    """The record's expected artifacts: one per ``produces`` path of each selected step (K4)."""
    selected = set(workflow_step_ids)
    artifacts: list[DataArtifact] = []
    for step in record.workflow_steps:
        if step.step_id not in selected:
            continue
        for index, path in enumerate(step.produces):
            artifacts.append(DataArtifact(
                artifact_id=record_artifact_id(step.step_id, index),
                path_pattern=path,
                format="file",
                description=f"{record.name} step {step.step_id!r} writes {path}",
                produced_by=step.step_id,
            ))
    return tuple(artifacts)


def commit_and_build_record_spec(
    record: TutorialRecord,
    *,
    case_id: str,
    cases_root: Path,
    staged_case_root: Path,
    study_by_source: Mapping[str, Mapping[str, Any]],
    driver_context: "DriverContext",
    execution_env: Any | None = None,
    requested_by: str = "tutorial_record",
) -> tuple[RecordCommitResult, Any]:
    """Stage, commit, and build the ``TutorialSpec`` for one record case --
    design §4 steps 1-8's write half plus the spec that maps the committed
    case onto the factory-tutorial workflow shape (``record_case_spec``).

    This is the ONE "stage + commit + spec" sequence a record case needs
    before it can be planned/run through ``strict_planning
    ._strict_plan_for_spec`` -- both ``sweep_runner`` (one case out of a
    sweep) and ``strict_planning.strict_plan`` (a single ``plan --strict
    --entry <record>`` invocation) call this, never each keeping its own
    copy (P1 fix, docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
    design.md, "Owner decisions" dated 2026-09-25: "Factor the shared
    'stage + commit + spec' sequence into ONE function that both
    sweep_runner and strict_plan call. No duplicate.").
    """
    commit_result = commit_record_case(
        record, cases_root=cases_root, staged_case_root=staged_case_root,
        study_by_source=study_by_source, driver_context=driver_context,
        execution_env=execution_env, requested_by=requested_by,
    )
    spec = record_case_spec(
        record, case_id=case_id, staged_case_root=staged_case_root,
        workflow_step_ids=commit_result.workflow_step_ids,
        command_arguments=commit_result.command_arguments,
    )
    return commit_result, spec


def record_case_spec(
    record: TutorialRecord,
    *,
    case_id: str,
    staged_case_root: Path,
    workflow_step_ids: tuple[str, ...],
    command_arguments: Mapping[str, tuple[str, ...]],
) -> Any:
    """Build the ``TutorialSpec`` a committed record case's workflow runs
    through -- the same ``strict_planning._strict_plan_for_spec``/run-
    document/workflow-runner pipeline a factory tutorial's ``case_folder``
    spec runs through (item 2: "map the record's steps onto the same
    workflow DAG shape factory tutorials use... through the existing
    workflow runner. do not build a second runner").

    The case's content was already written by ``commit_record_case`` before
    this is ever called -- design §4 step 7 (commit) happens strictly before
    step 8 (run). This spec's own case mutation is therefore a genuine no-op
    (``plan_case`` returning ``None``), never a second write: there is
    nothing left for it to do.

    ``metadata["generic_case"] = True`` matches ``generic_case.make_spec``'s
    own convention for a spec with no solver-specific config to validate --
    correct here for the same reason: a tutorial record is core-owned data,
    not a solver's config vocabulary, so there is no plugin config schema to
    validate a record spec's (empty) ``config`` against.
    """
    from .models import CaseConfig, TutorialSpec

    case_root = Path(staged_case_root)
    workflow_dag = _workflow_dag_for_record(
        record, workflow_step_ids=workflow_step_ids, command_arguments=command_arguments,
    )
    return TutorialSpec(
        name=case_id,
        case_root=case_root,
        setup_root=case_root,
        output_dir=case_root,
        build_cases=lambda: [CaseConfig(case_id=case_id, params={})],
        plan_case=lambda root, case: None,
        metadata={
            "entry_name": record.name,
            "entry_kind": "tutorial_record",
            "entry_path": record.native_case_relpath,
            "source_type": "tutorial_record",
            "workflow_family": None,
            "resolution": "tutorial_record",
            "workflow_dag": workflow_dag,
            "generic_case": True,
            "expected_artifacts": record_step_artifacts(record, workflow_step_ids),
        },
    )
