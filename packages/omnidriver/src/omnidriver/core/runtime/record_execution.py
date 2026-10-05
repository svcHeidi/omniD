"""Run one tutorial-record case: stage the native case, split its patches into changed/unchanged, commit the changed ones.

``preview_record_case`` never commits; ``commit_record_case`` does, through one ``commit_case_write`` call."""

from __future__ import annotations

import contextlib
import copy
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping, Sequence

from ..case_transaction import commit_case_write
from ..case_write import CaseKeyNotFound, CaseMutationRequest, CaseWritePlan, CaseWriteRecord, render_mutation, resolve_mutation
from ..provider_stack import MemberAbsent
from ..sweep.sweep_derivation_catalog import NAMING_OUTPUT_KEYS
from .models import DataArtifact
from ..tutorial_records import (
    PARALLEL_STUDY_NAME,
    ResolvedInput,
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    _strictly_equal,
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
    """Outcome of a record case's commit: what was written, what was already
    unchanged, and what its workflow needs to run.
    """

    write_record: CaseWriteRecord | None
    unchanged: tuple[SourcedPatch, ...]
    command_arguments: dict[str, tuple[str, ...]]
    #: The ordered step ids this case's workflow actually runs -- the
    #: record's own steps, or one selected variant's, per
    #: `_resolve_workflow_route`. Needed alongside `command_arguments` to
    #: build the DAG.
    workflow_step_ids: tuple[str, ...]
    #: The run's ``parallel`` request, ``None`` for serial (absent, or
    #: ``False``). Handed to the stack's parallel form (``record_case_spec``).
    parallel_request: Any = None
    #: Every input this case resolved (name, native/supplied, its path, its
    #: files) -- carried onto ``resolvedEntry.inputs`` by ``record_case_spec``.
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
    not carry over from a previous run.

    A produced path is excluded unless the first step (in workflow order)
    that touches it -- consumes or produces -- consumes it, meaning the
    path was already an authored input before this record ever produced it.
    A path a single step both consumes and produces, with no earlier
    producer, still counts as consumed first, so it is never excluded.
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
    """Stage the native case without input destinations, then overlay each resolved input; ``strict_inputs`` is off only for a preview."""
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
    """Study names that are neither a document key nor an axis and must not reach ``sort_study_name``."""
    reserved = NAMING_OUTPUT_KEYS | frozenset({PARALLEL_STUDY_NAME})
    if record.variant_selector is None:
        return reserved
    return reserved | frozenset({record.variant_selector})


def _parallel_request(record: TutorialRecord, reserved_values: Mapping[str, Any]) -> Any:
    """The study's ``parallel`` value, ``None`` for serial; a ``null`` is refused, not read as "no choice"."""
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
    """``(study_by_source without reserved names, reserved_values)``; sources must agree under ``_strictly_equal``, as ``1 == True``."""
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
    """The steps of the record or its selected variant, and that choice as ``describe`` reports it (``None`` without variants)."""
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
    validator, comparator, read_current_value = record_case_members(record, driver_context)
    study_by_source, reserved_values = _extract_reserved_names(
        study_by_source, reserved_names=_reserved_study_names(record),
    )
    workflow_step_ids, workflow_variant = _resolve_workflow_route(record, reserved_values)
    parallel_request = _parallel_request(record, reserved_values)
    combined, command_arguments = resolve_case_patches(
        record,
        study_by_source=study_by_source,
        staged_case_root=staged_case_root,
        direct_key_validator=validator,
        workflow_step_ids=workflow_step_ids,
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
    """``read_current_value`` with its ``ValueError`` turned into a ``TutorialRecordError`` naming record, document and key."""

    def read_or_refuse(document_path: Path, key_path: Any) -> Any:
        document = Path(document_path).relative_to(case_root).as_posix()
        with _refusal_as_record_error(
            record, frozenset({f"{document}:{'.'.join(key_path)}"}), "reading",
            refused_by="the config-value reader",
        ):
            return read_current_value(document_path, key_path)

    return read_or_refuse


def _serialize_sourced_patch(sourced: SourcedPatch, *, status: str) -> dict[str, Any]:
    """One patch's JSON shape, shared by the preview and the sweep manifest's ``unchanged_patches``."""
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
    """Copy each existing target document into ``snapshot_root`` so a renderer sees the prior content; a new one stays unseeded."""
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
    """Stage and resolve a record case without committing -- ``describe``'s
    preview.

    Stages the native case into a scratch directory that is discarded when
    this function returns; the real case (if one already exists at this
    entry's staged location) is never touched. Returns a JSON-shaped
    preview: every patch, its status (``"changed"``/``"unchanged"``), its
    document, key, value, and ``validated`` flag.
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
    """Each step's command line, read from the DAG so a parallel request's form is what the preview shows."""
    return {step["id"]: [step["command"], *step.get("args", ())] for step in dag["steps"]}


@contextlib.contextmanager
def _refusal_as_record_error(
    record: TutorialRecord, documents: frozenset[str], action: str,
    *, refused_by: str = "the case writer", scratch: Path | None = None,
) -> Iterator[None]:
    """Turn a ``ValueError`` or the writer's :class:`CaseKeyNotFound` into a ``TutorialRecordError`` naming the record; other errors propagate.
    ``scratch``, the temporary folder a renderer worked in, is dropped from the message so a document is named by its case path."""
    try:
        yield
    except TutorialRecordError:
        raise
    except (ValueError, CaseKeyNotFound) as exc:
        reason = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        if scratch is not None:
            for spelling in {str(scratch), str(scratch.resolve())}:
                reason = reason.replace(f"{spelling}/", "")
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: {action} {', '.join(sorted(documents))} "
            f"was refused by {refused_by} ({type(exc).__name__}): {reason}"
        ) from exc


def record_case_members(record: TutorialRecord, driver_context: "DriverContext") -> tuple[Any, Any, Any]:
    """The stack's record-key validator, case-value comparator and
    config-value reader, refused by name with the record when one is absent:
    without them a record case's keys go unchecked and every no-op patch
    looks like a change."""
    stack = driver_context.stack
    try:
        return (
            stack.call("get_record_key_validator"),
            stack.call("get_case_value_comparator"),
            stack.call("get_config_value_reader"),
        )
    except MemberAbsent as exc:
        raise TutorialRecordError(f"tutorial record {record.name!r} cannot run: {exc}") from exc


def refuse_a_case_that_breaks_a_rule(
    record: TutorialRecord, case_root: Path, driver_context: "DriverContext", *, then: str = "",
) -> None:
    """Refuse the resolved case by name, with each rule's own message, when
    the stack's catalogue relations, required keys or cross-field rules find
    an error in it: the one check every plan, run, sweep case, applied edit
    and run document passes before anything executes. ``then`` says what
    stays true after the refusal."""
    found = driver_context.stack.call("validate_run_semantics", case_root)
    broken = [item for item in found if item.level == "error"]
    if broken:
        noted = [item for item in found if item.level != "error"]
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: the resolved case breaks "
            f"{len(broken)} rule(s): "
            + "; ".join(f"{item.field or item.source}: {item.message}" for item in broken)
            + (" Also noted: " + "; ".join(item.message for item in noted) if noted else "")
            + then
        )


def _commit_patches(
    record: TutorialRecord,
    *,
    staged_case_root: Path,
    to_write: Sequence[SourcedPatch],
    driver_context: "DriverContext",
    execution_env: Any | None,
    requested_by: str,
    case_lease_held: bool = False,
    verify: Callable[[], None] | None = None,
) -> CaseWriteRecord:
    """Resolve, render and commit ``to_write`` into ``staged_case_root`` through one ``commit_case_write``; what ``verify`` raises rolls the commit back."""
    import tempfile

    identity = driver_context.identity
    adapter_id = identity.resolutions["resolve_case_mutation"]
    parameters = patches_to_parameters(to_write, owner=adapter_id)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=staged_case_root, adapter_id=adapter_id,
        workflow=record.name, source_artifacts=(), parameters=parameters,
        requested_by=requested_by,
    )
    documents = frozenset(parameter.document for parameter in parameters)
    with _refusal_as_record_error(record, documents, "resolving"):
        resolved = resolve_mutation(driver_context, request)
    # `snapshot_root` must be a directory distinct from `request.case_root`:
    # reusing it makes a real renderer's seeding copy a no-op `shutil.copy2`
    # onto itself, raising `shutil.SameFileError`. `_seed_snapshot_root`
    # seeds this scratch copy with the staged case's current bytes before a
    # renderer ever sees it.
    with tempfile.TemporaryDirectory(prefix="omnidriver-record-render-") as scratch:
        snapshot_root = Path(scratch)
        _seed_snapshot_root(
            snapshot_root, case_root=staged_case_root, documents=documents,
        )
        with _refusal_as_record_error(record, documents, "rendering", scratch=snapshot_root):
            rendered = render_mutation(
                driver_context, resolved, snapshot_root=snapshot_root, execution_env=execution_env,
            )
    plan = CaseWritePlan(
        request=request, files=tuple(rendered),
        semantic_owner_id=resolved.semantic_owner_id, stack_identity=identity.capability_digest,
        expected_effects=resolved.expected_effects,
    )
    return commit_case_write(
        plan, driver_context=driver_context, case_lease_held=case_lease_held, verify=verify,
    )


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
    """Stage, resolve, and commit one case in one ``commit_case_write``
    call.

    ``staged_case_root`` persists after this call (unlike
    ``preview_record_case``'s scratch clone) -- it is the sweep's real,
    per-case staging directory, the same one a later workflow-step run reads.

    Returns a :class:`RecordCommitResult` whose ``write_record`` is ``None``
    when every patch was already unchanged -- a legitimate no-op, not a
    failure, so nothing is committed and no transaction is created --
    reported explicitly via ``result.status``/``result.unchanged``.
    """
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
    write_record = None
    if to_write:
        write_record = _commit_patches(
            record, staged_case_root=staged_case_root, to_write=to_write,
            driver_context=driver_context, execution_env=execution_env,
            requested_by=requested_by,
        )
    refuse_a_case_that_breaks_a_rule(record, staged_case_root, driver_context)
    return RecordCommitResult(
        write_record=write_record, unchanged=unchanged, command_arguments=command_arguments,
        workflow_step_ids=workflow_step_ids, parallel_request=parallel_request,
        resolved_inputs=resolved_inputs,
    )


def apply_record_study(
    record: TutorialRecord,
    *,
    case_root: Path,
    study: Mapping[str, Any],
    driver_context: "DriverContext",
    execution_env: Any | None = None,
    check: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Edit an already staged case with ``document:key`` patches, the same a
    study takes, through the record's own validator, comparison and
    ``commit_case_write``. The caller holds the case lease.

    Refuses a name that is not a ``document:key``: an axis or reserved name
    changes the plan, which needs a new plan rather than an edit. An edit
    after which the case breaks a rule is rolled back, so a refusal leaves the
    case as it was, and so is one after which ``check`` raises. Returns every
    patch, serialized, as ``changed`` or ``unchanged``.
    """
    plan_changing = sorted(name for name in study if ":" not in name)
    if plan_changing:
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: {plan_changing} is not a 'document:key' "
            "patch; an axis or reserved name changes the plan, so plan again with it"
        )
    to_write, unchanged, *_ = _resolve_and_split(
        record, study_by_source={"apply": study}, staged_case_root=case_root,
        driver_context=driver_context,
    )

    def refuse_a_broken_case() -> None:
        refuse_a_case_that_breaks_a_rule(
            record, case_root, driver_context, then="; the case is as it was before the edit",
        )

    def verify() -> None:
        refuse_a_broken_case()
        if check is not None:
            check()

    if to_write:
        _commit_patches(
            record, staged_case_root=case_root, to_write=to_write,
            driver_context=driver_context, execution_env=execution_env,
            requested_by="step_apply", case_lease_held=True, verify=verify,
        )
    else:
        refuse_a_broken_case()
    return tuple(
        _serialize_sourced_patch(sourced, status=status)
        for status, patches in (("changed", to_write), ("unchanged", unchanged))
        for sourced in patches
    )


def _workflow_dag_for_record(
    record: TutorialRecord,
    *,
    workflow_step_ids: tuple[str, ...],
    command_arguments: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    """The selected steps as the ``{"steps": [...]}`` DAG, chained in declaration order, with axis arguments in ``WorkflowStep.argv``."""
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
# Serial versus parallel belongs to the solver's own layer: core finds the
# solve step, hands it over, and rewires the DAG.
# ---------------------------------------------------------------------------


#: Where core looks for the processes a batch scheduler allocated to this
#: job. Read only when a run asks for parallel: a scheduler's allocation is
#: an ambient fact (see CLAUDE.md's "supplied versus discovered"), so
#: discovering it is right, provided the place looked in is declared here.
#: Slurm's ``SLURM_NTASKS`` only; another scheduler is one more entry.
SCHEDULER_ALLOCATION_VARIABLES = ("SLURM_NTASKS",)


@dataclass(frozen=True)
class SchedulerAllocation:
    """How many processes the ambient scheduler allocated, and where that
    was read. Handed to the solver layer's parallel form, which decides
    what a disagreeing allocation means (a refusal in the shipped layers,
    never an override)."""

    variable: str
    ranks: int

    def to_json(self) -> dict[str, Any]:
        return {"variable": self.variable, "ranks": self.ranks}


def scheduler_allocation(environ: Mapping[str, str]) -> SchedulerAllocation | None:
    """The allocation from the first declared variable set, or ``None``; a non-positive-integer value is refused, not skipped."""
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
    """``read_value(document, key_path)`` for the parallel form: a ``pending`` patch's value, else the staged case's."""
    pending_values = {
        (sourced.patch.document, tuple(sourced.patch.key_path)): sourced.patch.value
        for sourced in pending
    }
    read = _reader_refusing_as_record_error(
        record, record_case_members(record, driver_context)[2], case_root=case_root,
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
    """``(dag, None)`` for a serial run; else the parallel DAG and the provenance of the request and its allocation."""
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
    """Replace each solve step with the stack's ``get_parallel_steps`` form; core checks only that ids and ``produces`` hold."""
    stack = driver_context.stack
    if record.serial_only:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} is serial only: the run asks for "
            f"{PARALLEL_STUDY_NAME!r} = {request!r}, but its solve has nothing to split across processes; "
            f"omit {PARALLEL_STUDY_NAME!r}, or set it false, to run serial"
        )
    if not stack.implements("get_parallel_steps"):
        raise TutorialRecordError(
            f"tutorial record {record.name!r}: the run asks for "
            f"{PARALLEL_STUDY_NAME!r} = {request!r}, but {stack.refusal('get_parallel_steps')}; "
            f"omit {PARALLEL_STUDY_NAME!r}, or set it false, to run serial"
        )
    solve_commands = stack.call("get_solve_step_commands")
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
                dict(entry) for entry in stack.call(
                    "get_parallel_steps", copy.deepcopy(step), request=request, read_value=read_value,
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
    """The record's expected artifacts: one per ``produces`` path of each selected step."""
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
    inputs: Mapping[str, str | Path] | None = None,
) -> tuple[RecordCommitResult, Any]:
    """Stage and commit one record case and build its ``TutorialSpec``: the
    one sequence both ``sweep_runner`` (a case of a sweep) and
    ``strict_planning.strict_plan`` (a single plan) run before planning.
    """
    commit_result = commit_record_case(
        record, cases_root=cases_root, staged_case_root=staged_case_root,
        study_by_source=study_by_source, driver_context=driver_context, inputs=inputs,
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
    """Build the ``TutorialSpec`` a committed record case's workflow plans and
    runs through. The case's content was written by ``commit_record_case``
    before this is called.

    A ``parallel_request`` (``RecordCommitResult``'s) rewrites the solve
    step into the stack's parallel form, reading the committed case; it
    needs the ``driver_context``, and a serial spec does not.
    ``metadata["parallel"]`` then records the request, and the run document
    carries it (``resolvedEntry.parallel``), so a serial and a parallel run
    of one case are told apart by more than their DAG digest.
    """
    from .models import TutorialSpec

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
        metadata={
            "entry_name": record.name,
            "entry_path": record.native_case_relpath,
            "workflow_dag": workflow_dag,
            "setup_root": str(case_root),
            "output_dir": str(case_root),
            "expected_artifacts": record_step_artifacts(record, workflow_step_ids),
            **metadata,
        },
    )
