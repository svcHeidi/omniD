"""Run one tutorial-record case: stage the native case, resolve and split
patches into changed/unchanged, and commit the changed ones through one
``commit_case_write`` call.

``preview_record_case`` stages and resolves without ever committing;
``commit_record_case`` also commits.
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
    """Copy the native case, excluding every input destination, then overlay
    each resolved input's files into the same staged clone.

    ``strict_inputs`` is ``False`` only for ``preview_record_case``: an
    unresolved or incomplete input is then silently left unstaged rather
    than refused.
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
    and must never reach ``sort_study_name``: the two sweep
    naming-derivation outputs (``NAMING_OUTPUT_KEYS``) and this record's own
    ``variant_selector`` name, if it declares one.
    """
    reserved = NAMING_OUTPUT_KEYS | frozenset({PARALLEL_STUDY_NAME})
    if record.variant_selector is None:
        return reserved
    return reserved | frozenset({record.variant_selector})


def _parallel_request(record: TutorialRecord, reserved_values: Mapping[str, Any]) -> Any:
    """The study's ``parallel`` value, or ``None`` for serial (absent, or
    ``False``). Any other value is the solver layer's to interpret. A
    ``null`` is refused by name rather than read as "no choice"."""
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
    conflicts across sources by name. Returns
    ``(stripped_study_by_source, reserved_values)``, the latter mapping each
    reserved name actually present to its one agreed value. Conflict is
    checked with strict same-type equality (``_strictly_equal``), not plain
    ``==``, since ``1`` and ``True`` compare equal under Python's numeric
    tower but may come from callers who each meant a different value.
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
    """The record's own steps, or one selected variant's steps, and which
    variant that is.

    A record that declares ``workflow_variants`` runs the variant the study
    names through the record's ``variant_selector``, or, when the study does
    not name the selector at all, the record's ``default_variant``. A study
    that names the selector with a value that is not a declared variant --
    ``None`` included -- is refused by ``resolve_variant_selector``, never
    read as "no choice" and defaulted. A record with no variants at all
    refuses a study that names its selector.

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
    # Neither capability has a compatibility fallback (`:fallback: none`) --
    # a stack missing a record-key validator or a case-value comparator
    # cannot run a tutorial-record case at all, and must say so by name
    # rather than silently accepting every key unchecked or reporting every
    # no-op patch as "changed" and writing it.
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
        # Must run before any axis runs or any patch is proposed.
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
    reader refusing the native value it found -- turned into a
    ``TutorialRecordError`` naming the record, the document and the key,
    the original chained. ``split_unchanged`` still lets the refusal
    propagate, never reading it as "changed"; only its type and message
    change."""

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
    and the sweep manifest/summary's own per-case ``unchanged_patches`` --
    one definition of "what a patch looks like on the wire", not two
    independently maintained ones."""
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
    ``snapshot_root`` before a renderer ever sees it, so a renderer that
    reads ``snapshot_root/<document>`` (per ``render_case_files``'s own
    isolated-copy contract) finds the real prior content rather than an
    empty directory. A document the case does not yet hold is left
    unseeded: the renderer legitimately sees it as new, the only situation
    where ``exists_before=False`` is true.
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
    """The command line each step of the DAG a run would build runs, as
    ``describe`` shows it: its command, the default arguments no axis
    replaced, and the axis's contribution (``WorkflowStep.argv``). Read
    from the DAG, not the record's steps, so a parallel request's form is
    what the preview shows."""
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
    original message and the original exception chained. A non-``ValueError``
    is a defect, not a refusal, and still propagates as itself.

    ``refused_by`` names the layer; the config-value reader uses it too,
    with ``document:key`` labels (:func:`_reader_refusing_as_record_error`)."""
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

    # `identity.resolutions["case_writer"]` names whichever provider in the
    # composed stack actually answers `case_writer` -- correct even when
    # that is not the most specific provider.
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
# Running a committed record case's workflow through the same workflow-DAG
# shape and the same planning/run machinery a factory tutorial uses -- no
# second runner.
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
    ``depends_on`` in declaration order -- core knows neither tool by name.

    An axis's command arguments for a step (``AxisResult.command_arguments``,
    already merged and conflict-checked by ``resolve_case_patches``) are
    appended after the step's own declared ``command`` tail and the default
    arguments they do not replace (``WorkflowStep.argv``).
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
    """``read_value(document, key_path)`` for the parallel form: a
    ``pending`` (not yet committed) patch's value if present, else the
    staged case's, through the stack's config-value reader."""
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
    """``dag`` unchanged and ``None`` for a serial run; otherwise the
    parallel DAG and what provenance records of the request: the requested
    value and the scheduler allocation the form was checked against (``None``
    outside a scheduler)."""
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
    execution_env: Any | None = None,
    requested_by: str = "tutorial_record",
    inputs: Mapping[str, str | Path] | None = None,
) -> tuple[RecordCommitResult, Any]:
    """Stage, commit, and build the ``TutorialSpec`` for one record case --
    the spec that maps the committed case onto the factory-tutorial
    workflow shape (``record_case_spec``).

    This is the one "stage + commit + spec" sequence a record case needs
    before it can be planned/run through ``strict_planning
    ._strict_plan_for_spec`` -- both ``sweep_runner`` (one case out of a
    sweep) and ``strict_planning.strict_plan`` (a single ``plan --strict
    --entry <record>`` invocation) call this, never each keeping its own
    copy.
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
    spec runs through, so there is no second runner.

    The case's content was already written by ``commit_record_case`` before
    this is ever called, so this spec's own ``case_mutation`` is a genuine
    no-op, never a second write.

    ``metadata["generic_case"] = True`` matches ``generic_case.make_spec``'s
    own convention for a spec with no solver-specific config to validate --
    correct here for the same reason: a tutorial record is core-owned data,
    not a solver's config vocabulary, so there is no plugin config schema to
    validate a record spec's (empty) ``config`` against.

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
        case_mutation=lambda root: None,
        metadata={
            "entry_name": record.name,
            "entry_kind": "tutorial_record",
            "entry_path": record.native_case_relpath,
            "source_type": "tutorial_record",
            "workflow_family": None,
            "resolution": "tutorial_record",
            "workflow_dag": workflow_dag,
            "setup_root": str(case_root),
            "output_dir": str(case_root),
            "generic_case": True,
            "expected_artifacts": record_step_artifacts(record, workflow_step_ids),
            **metadata,
        },
    )
