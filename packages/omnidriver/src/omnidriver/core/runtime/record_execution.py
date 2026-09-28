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
import copy
import datetime
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence

from ..case_transaction import commit_case_write
from ..case_write import CaseMutationRequest, CaseWritePlan, CaseWriteRecord
from ..sweep.sweep_derivation_catalog import NAMING_OUTPUT_KEYS
from .models import DataArtifact
from ..tutorial_records import (
    PARALLEL_STUDY_NAME,
    ResolvedInput,
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    _strictly_equal,
    check_variant_constraints,
    patches_to_parameters,
    record_input_destinations,
    resolve_case_patches,
    resolve_record_inputs,
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
    #: `_resolve_workflow_route`. The caller that runs the workflow (sweep
    #: dispatch) needs this alongside `command_arguments` to build the DAG.
    workflow_step_ids: tuple[str, ...]
    #: PAR (2026-09-26): the run's ``parallel`` request, ``None`` for serial
    #: (absent, or ``False``). The caller that builds the DAG hands it to
    #: the stack's parallel form (``record_case_spec``).
    parallel_request: Any = None
    #: Step S: every input this case resolved (name, native/supplied, its
    #: path, its files) -- ``record_case_spec`` carries it onto
    #: ``resolvedEntry.inputs``.
    resolved_inputs: tuple[ResolvedInput, ...] = ()

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


def record_generated_relpaths(record: TutorialRecord) -> frozenset[str]:
    """The case-relative paths a record's steps write, which staging must
    not carry from one run into the next stage (spec 2026-09-26 A5).

    Corrected 2026-09-26 (R1 fix, finding I2): this used to be "produced
    minus consumed", treating any path some step consumes as "an input
    updated in place", exempt from exclusion -- even when an EARLIER step
    produced that same path. That path is an intermediate, not an authored
    input (e.g. a mesh step's output a solve step reads): keeping it meant
    a restage carried a previous run's mesh forward. The rule is now: a
    produced path is excluded unless the FIRST step (in workflow order)
    that touches it -- consumes or produces -- consumes it, meaning the
    path was already an authored input before this record ever produced it.
    A path a single step both consumes and produces (rewritten in place,
    with no earlier producer) still counts as consumed first, so it is
    still never excluded.
    """
    first_touch: dict[str, str] = {}
    produced_overall: set[str] = set()
    for step in record.workflow_steps:
        step_consumes = {PurePosixPath(p).as_posix() for p in step.consumes}
        step_produces = {PurePosixPath(p).as_posix() for p in step.produces}
        produced_overall |= step_produces
        for path in step_consumes | step_produces:
            if path in first_touch:
                continue
            first_touch[path] = "consumes" if path in step_consumes else "produces"
    return frozenset(path for path in produced_overall if first_touch[path] != "consumes")


def _stage(
    record: TutorialRecord, *, cases_root: Path, staged_case_root: Path,
    driver_context: "DriverContext",
    inputs: Mapping[str, str | Path] | None = None,
    strict_inputs: bool = True,
) -> tuple[ResolvedInput, ...]:
    """Design §2.3: copy the native case, excluding every input destination,
    then overlay each resolved input's files into the same staged clone,
    inside the one staging lease ``_stage_entry_case`` already holds.

    ``strict_inputs`` is ``False`` only for ``preview_record_case``
    (``describe``): an unresolved or incomplete input is silently left
    unstaged rather than refused (§2.2, "describe does not refuse") --
    correct because a record with no ``axes`` reads nothing an unstaged
    input would have held, and a record's own ``axes`` contract already
    forbids writing the staged case it reads (`resolve_case_patches`'s
    purity check).
    """
    from .sweep_runner import _stage_entry_case

    native_case_root = _native_case_root(record, cases_root=cases_root)
    resolved_inputs = resolve_record_inputs(
        record, inputs, cases_root=cases_root, strict=strict_inputs,
    )
    overlays = tuple(pair for resolved in resolved_inputs for pair in resolved.overlays())
    excluded = record_generated_relpaths(record) | record_input_destinations(record)
    _stage_entry_case(
        native_case_root, staged_case_root, driver_context=driver_context,
        excluded_relpaths=excluded, overlays=overlays,
    )
    return resolved_inputs


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
    reserved = NAMING_OUTPUT_KEYS | frozenset({PARALLEL_STUDY_NAME})
    if record.variant_selector is None:
        return reserved
    return reserved | frozenset({record.variant_selector})


def _parallel_request(record: TutorialRecord, reserved_values: Mapping[str, Any]) -> Any:
    """PAR: the study's ``parallel`` value, or ``None`` for serial (absent,
    or ``False``). Any other value is the solver layer's to interpret. A
    ``null`` is refused by name rather than read as "no choice", as a null
    variant selector is (``resolve_variant_selector``)."""
    if PARALLEL_STUDY_NAME not in reserved_values:
        return None
    value = reserved_values[PARALLEL_STUDY_NAME]
    if value is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: {PARALLEL_STUDY_NAME!r} is null; "
            "omit it, or set it false, to run serial"
        )
    return None if value is False else value


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


def _resolve_workflow_route(
    record: TutorialRecord, reserved_values: Mapping[str, Any],
) -> tuple[tuple[str, ...], dict[str, Any] | None]:
    """Item 4: the record's own steps, or one selected variant's steps, and
    which variant that is.

    A record that declares ``workflow_variants`` runs the variant the study
    names through the record's ``variant_selector``, or, when the study does
    not name the selector at all, the record's ``default_variant`` (owner
    Q2, 2026-09-26). A study that names the selector with a value that is not
    a declared variant -- ``None`` included -- is refused by
    ``resolve_variant_selector``, never read as "no choice" and defaulted.
    A record with no variants at all refuses a study that names its
    selector ("declares no workflow_variants").

    Corrected 2026-09-26 (owner Q2): a variant record used to REQUIRE the
    study to name the selector, so ``describe`` with no study values (design
    §6's zero-change test, conformance C2) refused every variant record.

    The second value is ``None`` for a record without variants, otherwise
    the choice as ``describe`` reports it: the selector name, the selected
    variant, whether it came from the ``"study"`` or the record's
    ``"default"``, the default, and every declared variant.
    """
    selector_name = record.variant_selector
    named = selector_name is not None and selector_name in reserved_values
    if not record.workflow_variants:
        if named:
            resolve_variant_selector(record, reserved_values[selector_name])  # raises: no variants
        return record.step_ids(), None
    selected = reserved_values[selector_name] if named else record.default_variant
    steps = resolve_variant_selector(record, selected)
    return steps, {
        "selector": selector_name,
        "selected": selected,
        "source": "study" if named else "default",
        "default": record.default_variant,
        "declared": sorted(record.workflow_variants),
    }


def _resolve_and_split(
    record: TutorialRecord,
    *,
    study_by_source: Mapping[str, Mapping[str, Any]],
    staged_case_root: Path,
    driver_context: "DriverContext",
) -> tuple[
    tuple[SourcedPatch, ...], tuple[SourcedPatch, ...],
    dict[str, tuple[str, ...]], tuple[str, ...], dict[str, Any] | None, Any,
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
    workflow_step_ids, workflow_variant = _resolve_workflow_route(record, reserved_values)
    if workflow_variant is not None:
        # Review 54b I3: before any axis runs or any patch is proposed.
        check_variant_constraints(record, workflow_variant["selected"], study_by_source)
    parallel_request = _parallel_request(record, reserved_values)
    combined, command_arguments = resolve_case_patches(
        record,
        study_by_source=study_by_source,
        staged_case_root=staged_case_root,
        direct_key_validator=validator,
    )
    to_write, unchanged = split_unchanged(
        combined,
        case_root=staged_case_root,
        read_current_value=_reader_refusing_as_record_error(
            record, read_current_value, case_root=staged_case_root,
        ),
        values_agree=comparator,
    )
    return to_write, unchanged, command_arguments, workflow_step_ids, workflow_variant, parallel_request


def _reader_refusing_as_record_error(
    record: TutorialRecord, read_current_value: Any, *, case_root: Path,
) -> Any:
    """``read_current_value``, with a ``ValueError`` it raises -- the config
    reader refusing the native value it found, e.g. openCARP's F1/F10
    ``ParFormatError`` -- turned into a ``TutorialRecordError`` naming the
    record, the document and the key, the original chained (final review
    S-M1, 2026-09-25). The reader is the third layer that can refuse a
    record case, after the key validator and the case writer (I2's
    :func:`_refusal_as_record_error`); without this its refusal escaped
    ``plan --strict`` and ``describe`` as a traceback with empty stdout.
    ``split_unchanged`` still lets the refusal propagate, never reading it as
    "changed"; only its type and message change."""

    def read_or_refuse(document_path: Path, key_path: Any) -> Any:
        document = Path(document_path).relative_to(case_root).as_posix()
        with _refusal_as_record_error(
            record, frozenset({f"{document}:{'.'.join(key_path)}"}), "reading",
            refused_by="the config-value reader",
        ):
            return read_current_value(document_path, key_path)

    return read_or_refuse


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
    inputs: Mapping[str, str | Path] | None = None,
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
            driver_context=driver_context, inputs=inputs, strict_inputs=False,
        )
        (
            to_write, unchanged, command_arguments, workflow_step_ids, workflow_variant, parallel_request,
        ) = _resolve_and_split(
            record, study_by_source=study_by_source,
            staged_case_root=staged_case_root, driver_context=driver_context,
        )
        dag = _workflow_dag_for_record(
            record, workflow_step_ids=workflow_step_ids, command_arguments=command_arguments,
        )
        dag, parallel = _apply_parallel_request(
            record, dag, request=parallel_request, driver_context=driver_context,
            read_value=_case_value_reader(
                record, driver_context, case_root=staged_case_root, pending=to_write,
            ),
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
            "workflow_variant": workflow_variant,
            "parallel": parallel,
            "workflow_commands": _workflow_commands(dag),
        }


def _workflow_commands(dag: Mapping[str, Any]) -> dict[str, list[str]]:
    """The command line each step of the DAG a run would build runs, as
    ``describe`` shows it: its command, the default arguments no axis
    replaced, and the axis's contribution (``WorkflowStep.argv``; owner Q3,
    2026-09-26). The preview's ``command_arguments`` shows only what axes
    contributed, so without this a default argument was invisible before a
    run. Corrected 2026-09-26 (PAR): read from the DAG, not the record's
    steps, so a parallel request's form is what the preview shows."""
    return {step["id"]: [step["command"], *step.get("args", ())] for step in dag["steps"]}


@contextlib.contextmanager
def _refusal_as_record_error(
    record: TutorialRecord, documents: frozenset[str], action: str,
    *, refused_by: str = "the case writer",
) -> Iterator[None]:
    """A ``ValueError`` the plugin's case writer raises while resolving or
    rendering -- its contract's refusal type, e.g. a renderer refusing a
    value the key validator could not see was wrong -- becomes a
    ``TutorialRecordError`` naming the record and the document(s), with the
    original message and the original exception chained (wave-2 review I2).

    Without this, ``plan --strict`` reported a validator refusal as JSON but a
    renderer refusal as a traceback on stderr with empty stdout: the shape of
    a refusal depended on which layer refused. A non-``ValueError`` is a
    defect, not a refusal, and still propagates as itself.

    ``refused_by`` names the layer; the config-value reader uses it too, with
    ``document:key`` labels (final review S-M1,
    :func:`_reader_refusing_as_record_error`)."""
    try:
        yield
    except TutorialRecordError:
        raise
    except ValueError as exc:
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: {action} {', '.join(sorted(documents))} "
            f"was refused by {refused_by} ({type(exc).__name__}): {exc}"
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
    inputs: Mapping[str, str | Path] | None = None,
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

    resolved_inputs = _stage(
        record, cases_root=cases_root, staged_case_root=staged_case_root,
        driver_context=driver_context, inputs=inputs,
    )
    (
        to_write, unchanged, command_arguments, workflow_step_ids, _variant, parallel_request,
    ) = _resolve_and_split(
        record, study_by_source=study_by_source,
        staged_case_root=staged_case_root, driver_context=driver_context,
    )
    if not to_write:
        return RecordCommitResult(
            write_record=None, unchanged=unchanged, command_arguments=command_arguments,
            workflow_step_ids=workflow_step_ids, parallel_request=parallel_request,
            resolved_inputs=resolved_inputs,
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
        workflow_step_ids=workflow_step_ids, parallel_request=parallel_request,
        resolved_inputs=resolved_inputs,
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
    appended after the step's own declared ``command`` tail and the default
    arguments they do not replace (``WorkflowStep.argv``; owner Q3,
    2026-09-26).
    """
    steps_by_id = {step.step_id: step for step in record.workflow_steps}
    dag_steps: list[dict[str, Any]] = []
    depends_on: list[str] = []
    for step_id in workflow_step_ids:
        step = steps_by_id[step_id]
        argv = list(step.argv(command_arguments.get(step_id, ())))
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


# ---------------------------------------------------------------------------
# PAR (owner Q6, 2026-09-26): serial versus parallel belongs to the solver's
# own layer. Core finds the solve step, hands it over, and rewires the DAG.
# ---------------------------------------------------------------------------


#: Where core looks for the processes a batch scheduler allocated to this
#: job. It is the one execution resource core reads, and it is read only
#: when a run asks for parallel: a scheduler's allocation is an ambient
#: fact (CLAUDE.md, "supplied versus discovered"; ENVIRONMENT_CONTRACT §12),
#: so discovering it is right, provided the place looked in is declared --
#: this tuple is that declaration. Slurm's ``SLURM_NTASKS`` only, the one
#: scheduler the owner's campaign runs on; another is one more entry.
SCHEDULER_ALLOCATION_VARIABLES = ("SLURM_NTASKS",)


@dataclass(frozen=True)
class SchedulerAllocation:
    """How many processes the ambient scheduler allocated, and where that
    was read. Handed to the solver layer's parallel form, which decides
    what an allocation that disagrees with its own count means (always a
    refusal by name in the shipped layers, never an override)."""

    variable: str
    ranks: int

    def to_json(self) -> dict[str, Any]:
        return {"variable": self.variable, "ranks": self.ranks}


def scheduler_allocation(environ: Mapping[str, str]) -> SchedulerAllocation | None:
    """The allocation ``environ`` states, from the first declared variable
    that is set, or ``None`` outside a scheduler. A value that is not a
    positive integer is refused by name, never skipped."""
    for variable in SCHEDULER_ALLOCATION_VARIABLES:
        raw = environ.get(variable)
        if raw is None:
            continue
        try:
            ranks = int(raw.strip())
        except ValueError:
            ranks = 0
        if ranks < 1:
            raise TutorialRecordError(
                f"the scheduler allocation {variable}={raw!r} is not a positive "
                "integer; a parallel run cannot check its process count against it"
            )
        return SchedulerAllocation(variable=variable, ranks=ranks)
    return None


def _case_value_reader(
    record: TutorialRecord, driver_context: "DriverContext", *, case_root: Path,
    pending: Sequence[SourcedPatch] = (),
):
    """``read_value(document, key_path)`` for the parallel form: the value
    the run's case will hold -- a ``pending`` (not yet committed) patch's
    value, else the staged case's, through the stack's config-value reader.
    The preview passes its uncommitted patches, so ``describe`` shows the
    form the committed case will get; the commit path passes none, because
    by then they are on disk."""
    pending_values = {
        (sourced.patch.document, tuple(sourced.patch.key_path)): sourced.patch.value
        for sourced in pending
    }
    read = _reader_refusing_as_record_error(
        record, driver_context.capabilities.config_value.reader(), case_root=case_root,
    )

    def read_value(document: str, key_path: Sequence[str]) -> Any:
        key = (document, tuple(key_path))
        if key in pending_values:
            return pending_values[key]
        return read(Path(case_root) / document, tuple(key_path))

    return read_value


def _apply_parallel_request(
    record: TutorialRecord, dag: dict[str, Any], *, request: Any,
    driver_context: "DriverContext", read_value: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """``dag`` unchanged and ``None`` for a serial run; otherwise the parallel
    DAG and what provenance records of the request: the requested value and
    the scheduler allocation the form was checked against (``None`` outside
    a scheduler). The allocation is read here, lazily, only for a parallel
    run."""
    if request is None:
        return dag, None
    allocation = scheduler_allocation(os.environ)
    parallel_dag = _parallel_workflow_dag(
        record, dag, request=request, driver_context=driver_context,
        read_value=read_value, allocation=allocation,
    )
    return parallel_dag, {
        "requested": request,
        "allocation": allocation.to_json() if allocation is not None else None,
    }


def _parallel_workflow_dag(
    record: TutorialRecord, dag: Mapping[str, Any], *, request: Any,
    driver_context: "DriverContext", read_value: Any,
    allocation: SchedulerAllocation | None,
) -> dict[str, Any]:
    """Replace each step whose command the stack declares a solve command
    (``get_solve_step_commands``, the record's solve step, declared once)
    with the parallel form the stack's ``get_parallel_steps`` returns, and
    make the next step follow the form's last step.

    Core checks only what keeps the rest of the run honest: the form keeps
    the solve step's id and ``produces`` on exactly one step (its artifacts
    and the record's declared outputs stay where they were), and takes no id
    another step already uses. What the form means -- a decomposition, a
    launcher, a rank count -- is the solver layer's. Every refusal names the
    record."""
    form = driver_context.capabilities.parallel_execution.steps_for()
    if form is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: the run asks for "
            f"{PARALLEL_STUDY_NAME!r} = {request!r}, but the composed stack declares no "
            "parallel form (get_parallel_steps), so it runs serial only; omit "
            f"{PARALLEL_STUDY_NAME!r}, or set it false, to run serial"
        )
    solve_commands = driver_context.capabilities.runtime_evidence.solve_step_commands()
    if not any(step["command"] in solve_commands for step in dag["steps"]):
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: the run asks for {PARALLEL_STUDY_NAME!r}, "
            f"but none of its selected steps {[step['id'] for step in dag['steps']]} runs a "
            f"solve command the stack declares (get_solve_step_commands: "
            f"{sorted(solve_commands)}), so there is no solve step to run in parallel"
        )
    taken = {step["id"] for step in dag["steps"]}
    steps: list[dict[str, Any]] = []
    follows: dict[str, str] = {}
    for serial_step in dag["steps"]:
        step = {**serial_step, "depends_on": [follows.get(d, d) for d in serial_step["depends_on"]]}
        if step["command"] not in solve_commands:
            steps.append(step)
            continue
        try:
            replacement = [
                dict(entry) for entry in form(
                    copy.deepcopy(step), request=request, read_value=read_value,
                    allocation=allocation,
                )
            ]
        except ValueError as exc:
            raise TutorialRecordError(
                f"tutorial record {record.name!r}: the solver layer refused the parallel "
                f"form of step {step['id']!r} ({type(exc).__name__}): {exc}"
            ) from exc
        _check_parallel_form(record, step, replacement, taken=taken)
        taken |= {entry["id"] for entry in replacement}
        steps.extend(replacement)
        follows[step["id"]] = replacement[-1]["id"]
    return {**dag, "steps": steps}


def _check_parallel_form(
    record: TutorialRecord, step: Mapping[str, Any], replacement: Sequence[Mapping[str, Any]],
    *, taken: set[str],
) -> None:
    where = f"tutorial record {record.name!r}: the parallel form of step {step['id']!r}"
    if not replacement:
        raise TutorialRecordError(f"{where} returned no steps")
    keeping = [entry for entry in replacement if entry.get("id") == step["id"]]
    if len(keeping) != 1:
        raise TutorialRecordError(
            f"{where} must keep the solve step's id {step['id']!r} on exactly one step; "
            f"it returned ids {[entry.get('id') for entry in replacement]}"
        )
    if list(keeping[0].get("produces", ())) != list(step["produces"]):
        raise TutorialRecordError(
            f"{where} must keep its produces {step['produces']} on the step that runs "
            f"the solver; it returned {keeping[0].get('produces')}"
        )
    for entry in replacement:
        if entry is not keeping[0] and entry.get("id") in taken:
            raise TutorialRecordError(
                f"{where} returned step id {entry.get('id')!r}, which the workflow already uses"
            )


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
                format=step.produced_format(path),
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
    inputs: Mapping[str, str | Path] | None = None,
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
        execution_env=execution_env, requested_by=requested_by, inputs=inputs,
    )
    spec = record_case_spec(
        record, case_id=case_id, staged_case_root=staged_case_root,
        workflow_step_ids=commit_result.workflow_step_ids,
        command_arguments=commit_result.command_arguments,
        parallel_request=commit_result.parallel_request,
        resolved_inputs=commit_result.resolved_inputs,
        driver_context=driver_context,
    )
    return commit_result, spec


def record_case_spec(
    record: TutorialRecord,
    *,
    case_id: str,
    staged_case_root: Path,
    workflow_step_ids: tuple[str, ...],
    command_arguments: Mapping[str, tuple[str, ...]],
    parallel_request: Any = None,
    resolved_inputs: tuple[ResolvedInput, ...] = (),
    driver_context: "DriverContext | None" = None,
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

    PAR (2026-09-26): a ``parallel_request`` (``RecordCommitResult``'s)
    rewrites the solve step into the stack's parallel form, reading the
    committed case; it needs the ``driver_context``, and a serial spec does
    not. ``metadata["parallel"]`` then records the request, and the run
    document carries it (``resolvedEntry.parallel``), so a serial and a
    parallel run of one case are told apart by more than their DAG digest.
    """
    from .models import CaseConfig, TutorialSpec

    case_root = Path(staged_case_root)
    workflow_dag = _workflow_dag_for_record(
        record, workflow_step_ids=workflow_step_ids, command_arguments=command_arguments,
    )
    parallel = None
    if parallel_request is not None:
        if driver_context is None:
            raise TutorialRecordError(
                f"tutorial record {record.name!r}: a parallel request needs the "
                "driver context whose stack provides the parallel form"
            )
        workflow_dag, parallel = _apply_parallel_request(
            record, workflow_dag, request=parallel_request, driver_context=driver_context,
            read_value=_case_value_reader(record, driver_context, case_root=case_root),
        )
    metadata: dict[str, Any] = {}
    if parallel is not None:
        metadata["parallel"] = parallel
    if resolved_inputs:
        metadata["inputs"] = [resolved.to_json() for resolved in resolved_inputs]
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
            **metadata,
        },
    )
