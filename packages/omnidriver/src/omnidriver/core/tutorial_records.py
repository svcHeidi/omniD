"""A tutorial record: data, not a factory -- and the axis contract it draws on.

Design: ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
§3 ("Components and ownership"), §4 ("One case, step by step"), §5 (refusals,
and the exception for a key an environment owns but has no full catalog for
yet).

**Why this is a separate module from ``core.case_write``.** A tutorial
record's native case is never written in place (§4 step 3: "The native tree
is never written"). Everything in this module runs against a disposable
staged clone and stops at *proposing* patches -- ``AxisPatch``,
``SourcedPatch`` -- which know a document, a key path, a value and how
validated the adapter considers it, but nothing about ``owner``/``workflow``/
bindings, the identity fields a real ``case_write.ParameterAssignment``
needs to actually commit. ``patches_to_parameters`` is the one seam between
the two: it promotes a merged, conflict-checked set of ``SourcedPatch``
into real ``ParameterAssignment``s, once, right before the single
``commit_case_write`` call (§4 step 7, "One case, step by step").

Zero solver-specific vocabulary lives here, and none may be added --
``scripts/check-import-boundaries.py`` enforces that on the import side, the
same way it guards every other core module.

**Corrected 2026-09-24 (review finding m5):** this used to also claim "the
core vocabulary tests" guard this module. No test does: the two tests that
name is short for (``test_core_declares_no_phase_vocabulary``,
``test_core_exports_no_phase_vocabulary``) each check one specific,
different module (``contracts.dictionary``, ``runtime.run_model``,
``dict_entries``) for a leftover ``Phase`` re-export, and neither imports or
scans this module at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from .case_write import _check_case_relative
from .contracts.dictionary import validate_value_shape


class TutorialRecordError(ValueError):
    """A tutorial-record study refused a name, a conflict, or a missing case.

    Every raise site names the offending key or source, per design §5's "BY
    NAME" requirement -- a caller catching this and printing ``str(exc)``
    already has enough to act on, with no need to inspect a structured
    payload.
    """


# ---------------------------------------------------------------------------
# The record itself
# ---------------------------------------------------------------------------


PARALLEL_STUDY_NAME = "parallel"
"""The one study name core reserves for how a record case runs (PAR, owner
Q6, 2026-09-26). Absent or ``False``: serial, the native default. Any other
value asks the composed stack's solver layer for the parallel form of the
record's solve step, and is handed to it as is: core gives it no meaning
(``record_execution._parallel_workflow_dag``). The CLI's ``--parallel`` is
the same request from another source. Core reserves it, rather than each
record or plugin declaring its own, because the request is a property of a
run, not of a record's content: one spelling for every solver is what lets
a scheduler job script ask for it without knowing which stack it drives.
No record may name an axis or its variant selector this."""


PLAIN_FILE_FORMAT = "file"
"""The format of a ``produces`` path that names none: a file that exists or
not, which no reader reads (``record_execution.record_step_artifacts``)."""


class ProducedPath(str):
    """A ``produces`` path that also names the format of what it holds.

    It *is* its path: a ``str`` equal to the path, so every reader of
    ``WorkflowStep.produces`` (the DAG's artifact ids, record staging,
    provenance, a JSON dump) sees paths exactly as before. The format rides
    on the entry and is read only through :meth:`WorkflowStep.produced_format`:
    a string operation on the path returns a plain ``str`` without it, and
    two entries compare equal by path alone. Core never interprets the
    format. It names the reader a plugin returns from
    ``get_artifact_value_reader`` (docs/superpowers/specs/2026-09-26-results-
    as-quantities-design.md §3). Added 2026-09-26.
    """

    format: str

    def __new__(cls, path: str, format: str) -> "ProducedPath":
        if not isinstance(path, str):
            raise TutorialRecordError(f"a produced path must be a str, not {type(path).__name__}")
        if not isinstance(format, str) or not format or format != format.strip():
            raise TutorialRecordError(
                f"produced path {path!r} must name a non-empty format without surrounding spaces, got {format!r}"
            )
        if format == PLAIN_FILE_FORMAT:
            raise TutorialRecordError(
                f"produced path {path!r}: format {PLAIN_FILE_FORMAT!r} is what a plain path already means; write the path alone"
            )
        entry = super().__new__(cls, path)
        entry.__dict__["format"] = format
        return entry

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"ProducedPath is immutable; cannot set {name!r}")

    def __reduce__(self):
        return (ProducedPath, (str(self), self.format))

    def __repr__(self) -> str:
        return f"ProducedPath({str(self)!r}, format={self.format!r})"


def _token_runs(tokens: Sequence[str], key: Sequence[str]) -> list[int]:
    """Every index where ``key`` occurs in ``tokens`` as a contiguous run,
    compared token by token for equality (overlapping runs counted)."""
    width = len(key)
    key = tuple(key)
    return [i for i in range(len(tokens) - width + 1) if tuple(tokens[i:i + width]) == key]


def _first_touching_step(
    path_str: str, steps: Sequence["WorkflowStep"],
) -> tuple[int, str] | None:
    """The index of the first step (in declared order) that touches
    ``path_str`` -- exactly, or through a directory relationship in either
    direction (a step consuming ``constant/polyMesh/boundary`` touches a
    destination of ``constant/polyMesh``, and vice versa) -- and whether it
    was through that step's ``consumes`` or its ``produces``. ``None`` if no
    step touches it at all. Shared by :meth:`TutorialRecord._check_inputs`
    (§2.1's two input/step refusals)."""
    path = PurePosixPath(path_str)

    def _touches(other: str) -> bool:
        other_path = PurePosixPath(str(other))
        return other_path == path or path in other_path.parents or other_path in path.parents

    for index, step in enumerate(steps):
        if any(_touches(p) for p in step.consumes):
            return index, "consumes"
        if any(_touches(p) for p in step.produces):
            return index, "produces"
    return None


def _any_step_consumes(path_str: str, steps: Sequence["WorkflowStep"]) -> bool:
    path = PurePosixPath(path_str)
    for step in steps:
        for consumed in step.consumes:
            consumed_path = PurePosixPath(str(consumed))
            if consumed_path == path or path in consumed_path.parents or consumed_path in path.parents:
                return True
    return False


def _string_tokens(label: str, value: Any, *, allow_empty_tuple: bool, allow_empty_token: bool) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TutorialRecordError(f"{label} must be a sequence of strings, not the bare string {value!r}")
    tokens = tuple(value)
    if not tokens and not allow_empty_tuple:
        raise TutorialRecordError(f"{label} must hold at least one token")
    for token in tokens:
        if not isinstance(token, str):
            raise TutorialRecordError(f"{label} {list(tokens)!r} holds {token!r}, which is not a str")
        if not token and not allow_empty_token:
            raise TutorialRecordError(f"{label} {list(tokens)!r} holds an empty token")
    return tokens


@dataclass(frozen=True)
class DefaultArgument:
    """An argument a workflow step passes unless an axis passes its own
    (owner Q3/Q7, 2026-09-26).

    On the command line it is ``key`` followed by ``values``: ``key=("-dict",),
    values=("system/blockMeshDict.3D",)`` passes ``-dict
    system/blockMeshDict.3D``, and ``key=("-setnumber", "lc"), values=("0.1",)``
    passes ``-setnumber lc 0.1``. The default is the step's own, copied from
    the native case, and independent of any study.

    **The replacement rule.** An axis replaces a default by passing the
    default's ``key`` tokens, contiguously, anywhere in its
    ``AxisResult.command_arguments`` for that step; the default's own tokens
    are then dropped, and the axis's contribution is appended as always. An
    axis that does not pass the ``key`` appends, and the default stays. So a
    ``dimension`` axis passing ``-dict system/blockMeshDict.1D`` gives
    ``blockMesh -dict system/blockMeshDict.1D``, never two ``-dict``s, and a
    gmsh axis passing ``-setnumber lc 0.05`` replaces a ``-setnumber lc``
    default but not a ``-setnumber nx`` one.

    ``key`` is as many tokens as name the argument: one for ``-dict``, two
    for ``-setnumber lc``, whose flag alone names nothing. Core compares
    tokens for equality and nothing more; it parses no flag and knows no
    arity.

    **Loose by design** (owner, 2026-09-26, "the pre-processing stage"): the
    record declares only the default, never the values that may replace it.
    Whatever an axis passes after the key -- ``-dict system/blockMeshDict.2D``,
    a dictionary an agent composed, any ``-setnumber lc`` -- replaces the
    default as passed; nothing checks it against the record. Only malformed
    input and real ambiguity are refused, below.

    **Ambiguity is refused, by name.** At construction
    (``WorkflowStep.__post_init__``), each default's ``key`` must occur
    exactly once, as a contiguous run, in the step's default command line
    (``command`` plus every default's tokens). That refuses a key the
    command already holds, two defaults with one key, and a key inside
    another default's tokens (``-setnumber`` beside ``-setnumber lc``). At
    resolution (``WorkflowStep.argv``), an axis contribution holding one key
    more than once is refused: it would pass the argument twice.
    """

    key: tuple[str, ...]
    values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _string_tokens(
            "a default argument's key", self.key, allow_empty_tuple=False, allow_empty_token=False,
        ))
        object.__setattr__(self, "values", _string_tokens(
            f"default argument {list(self.key)!r}'s values", self.values,
            allow_empty_tuple=True, allow_empty_token=True,
        ))

    def tokens(self) -> tuple[str, ...]:
        return self.key + self.values


class RecordInputError(TutorialRecordError):
    """A record input's declaration, or its resolution, was refused by name."""


class RecordInputNotSupplied(RecordInputError):
    """A record input has no native location, and none was supplied."""


class RecordInputIncomplete(RecordInputError):
    """A record input resolved to a directory missing one of its files."""


def _check_input_relative(label: str, value: str) -> tuple[str, ...]:
    """A record-input source or destination: case-relative shape, plus the
    two extra refusals every ``produces``/``consumes`` path already gets
    (``WorkflowStep.__post_init__``): no ``{``/``}``, and never the root
    itself."""
    if not isinstance(value, str) or not value:
        raise TutorialRecordError(f"{label} must be a non-empty str, got {value!r}")
    if "{" in value or "}" in value:
        raise TutorialRecordError(f"{label} must not contain '{{' or '}}': placeholders are not supported")
    try:
        parts = _check_case_relative(label, value).parts
    except ValueError as exc:
        raise TutorialRecordError(str(exc)) from exc
    if not parts:
        raise TutorialRecordError(f"{label} must not be the case root")
    return parts


@dataclass(frozen=True)
class RecordInput:
    """Data a record's steps read but that is not in its native case folder
    (design §2.1): a patient anatomy bundle, a shared mesh, a 1D graph.

    ``files`` is a tuple of ``(path inside the input, case-relative
    destination)`` pairs -- ``(".", destination)`` takes the input's own
    root (which may itself be a file, e.g. one graph file). ``native_relpath``
    is this input's default location under the environment's own cases root
    (native fact, e.g. the idealized heart's tracked ``../mesh``); ``None``
    means the input has no ambient location and must always be supplied
    (``--input NAME=PATH``).

    Checked here: a non-empty name, at least one file pair, every source and
    destination shaped like a real case-relative path (no absolute path, no
    ``..`` escape, no ``{``/``}``, never the root). Two destinations
    conflicting with each other, or with a step's own consumes/produces, are
    checked on the owning :class:`TutorialRecord` instead (§2.1's remaining
    rules), because only the record knows its own steps.
    """

    name: str
    files: tuple[tuple[str, str], ...]
    native_relpath: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise TutorialRecordError("a record input must have a non-empty name")
        if isinstance(self.files, str):
            raise TutorialRecordError(
                f"record input {self.name!r} files must be a sequence of (source, destination) "
                f"pairs, not the bare string {self.files!r}"
            )
        pairs = tuple(self.files)
        if not pairs:
            raise TutorialRecordError(f"record input {self.name!r} must declare at least one file")
        checked: list[tuple[str, str]] = []
        for pair in pairs:
            pair = tuple(pair)
            if len(pair) != 2:
                raise TutorialRecordError(
                    f"record input {self.name!r} file {pair!r} must be a (source, destination) pair"
                )
            source, destination = pair
            if source != ".":
                _check_input_relative(f"record input {self.name!r}'s source {source!r}", source)
            _check_input_relative(f"record input {self.name!r}'s destination {destination!r}", destination)
            checked.append((source, destination))
        object.__setattr__(self, "files", tuple(checked))
        if self.native_relpath is not None:
            _check_input_relative(
                f"record input {self.name!r}'s native_relpath {self.native_relpath!r}", self.native_relpath,
            )

    def destinations(self) -> tuple[str, ...]:
        return tuple(destination for _source, destination in self.files)


@dataclass(frozen=True)
class ResolvedInput:
    """One input, resolved to a real directory (or file), for staging and
    for provenance (§2.4's ``resolvedEntry.inputs``)."""

    name: str
    kind: str  # "native" | "supplied"
    path: Path
    files: tuple[tuple[str, str], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "path": str(self.path),
            "files": [list(pair) for pair in self.files],
        }

    def overlays(self) -> tuple[tuple[Path, str], ...]:
        return tuple(
            (self.path if source == "." else self.path / source, destination)
            for source, destination in self.files
        )


def resolve_record_inputs(
    record: "TutorialRecord",
    supplied: Mapping[str, str | Path] | None,
    *,
    cases_root: Path,
    strict: bool = True,
) -> tuple[ResolvedInput, ...]:
    """Resolve every input a record declares (design §2.2).

    A supplied path wins; otherwise the input's own native location, if it
    has one; otherwise -- when ``strict`` -- refused by name
    (:class:`RecordInputNotSupplied`). An input whose resolved directory is
    missing one of its declared files is refused too
    (:class:`RecordInputIncomplete`), naming the missing files.

    ``strict=False`` is ``describe``'s own posture (§2.2: "describe does not
    refuse"): an input with nothing to resolve, or an incomplete one, is
    left out of the result rather than raising -- an agent learns the
    record's input NAMES from :mod:`record_surface` before it has the data.
    An unknown ``--input`` name is refused either way: that is a typo in
    what the caller asked for, not a question of whether data exists yet.
    """
    supplied = dict(supplied or {})
    declared = {input_.name: input_ for input_ in record.inputs}
    unknown = sorted(set(supplied) - set(declared))
    if unknown:
        raise RecordInputError(
            f"tutorial record {record.name!r} does not declare input(s) {unknown}; "
            f"it declares {sorted(declared) or 'none'}"
        )
    resolved: list[ResolvedInput] = []
    for name, input_ in declared.items():
        if name in supplied:
            path, kind = Path(supplied[name]).expanduser(), "supplied"
        elif input_.native_relpath is not None:
            path, kind = Path(cases_root) / input_.native_relpath, "native"
        elif strict:
            files = ", ".join(source for source, _dest in input_.files)
            raise RecordInputNotSupplied(
                f"record {record.name!r} needs input {name!r} "
                f"({len(input_.files)} files: {files}); it has no native "
                f"location; supply --input {name}=<dir>"
            )
        else:
            continue
        missing = [
            source for source, _dest in input_.files
            if not (path if source == "." else path / source).exists()
        ]
        if missing:
            if strict:
                raise RecordInputIncomplete(
                    f"record {record.name!r} input {name!r} at {path} is missing file(s): {missing}"
                )
            continue
        resolved.append(ResolvedInput(name=name, kind=kind, path=path, files=input_.files))
    return tuple(resolved)


@dataclass(frozen=True)
class WorkflowStep:
    """One named step in a tutorial record's workflow.

    ``command`` is the step's base argv; an axis may contribute additional
    arguments for a step it names (``AxisResult.command_arguments``),
    appended after the base (see ``resolve_case_patches``). Core does not
    know what any of these strings mean -- the solver binary's own name, or
    a mesh-generation tool's flags, are the adapter's own vocabulary.

    ``default_arguments`` are arguments the step passes unless an axis
    passes its own; :class:`DefaultArgument` states the replacement rule.
    The step runs :meth:`argv`: ``command``, then every default no axis
    replaced (in declared order), then the axis's contribution. Added
    2026-09-26 (owner Q3/Q7).

    ``produces`` and ``consumes`` are case-relative paths the step writes
    and reads (K4, docs/superpowers/specs/2026-09-25-solver-conformance-
    and-opencarp-design.md §5). ``produces`` becomes the record's expected
    artifacts; ``consumes`` becomes the step's DAG ``consumes``, which
    provenance fingerprints. Paths here, never artifact ids: the ids are
    derived (``record_execution.record_artifact_id``).

    A step whose command has a utility manifest keeps the manifest's
    ``produces`` beside its own: ``runtime.workflow.normalize_workflow_dag``
    takes the union, never a replacement (fix round 1 I6, 2026-09-25).

    Each is a tuple of non-empty, case-relative ``str`` paths (fix round 1
    M1, 2026-09-25): a bare ``str`` is refused rather than exploded into
    one-character paths; ``""`` and ``"."`` (the case root itself) are
    refused; so are ``{`` and ``}``, because a ``produces`` path becomes an
    artifact ``path_pattern`` that core ``str.format``-s -- the
    ``{case_id}``/``{instance}`` placeholders are not supported here.

    A ``produces`` entry may be a :class:`ProducedPath`, which also names its
    format. A plain path means :data:`PLAIN_FILE_FORMAT`. Added 2026-09-26.
    """

    step_id: str
    command: tuple[str, ...]
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    default_arguments: tuple[DefaultArgument, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        if isinstance(self.default_arguments, DefaultArgument):
            raise TutorialRecordError(
                f"workflow step {self.step_id!r} default_arguments must be a sequence of DefaultArgument, not one"
            )
        object.__setattr__(self, "default_arguments", tuple(self.default_arguments))
        for default in self.default_arguments:
            if not isinstance(default, DefaultArgument):
                raise TutorialRecordError(
                    f"workflow step {self.step_id!r} default_arguments holds {default!r}, which is not a DefaultArgument"
                )
        default_line = self.command + tuple(token for d in self.default_arguments for token in d.tokens())
        for default in self.default_arguments:
            count = len(_token_runs(default_line, default.key))
            if count != 1:
                raise TutorialRecordError(
                    f"workflow step {self.step_id!r}: default argument key {list(default.key)!r} must occur "
                    f"exactly once in the step's default command line {list(default_line)!r}, and occurs "
                    f"{count} times; an axis passing it could not say which argument it replaces"
                )
        for field_name in ("produces", "consumes"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                raise TutorialRecordError(
                    f"workflow step {self.step_id!r} {field_name} must be a sequence "
                    f"of paths, not the bare string {value!r}"
                )
            object.__setattr__(self, field_name, tuple(value))
        if not self.step_id:
            raise TutorialRecordError("a workflow step must have a non-empty step_id")
        if not self.command:
            raise TutorialRecordError(
                f"workflow step {self.step_id!r} must have a non-empty "
                "command -- there is nothing to run"
            )
        for field_name in ("produces", "consumes"):
            for path in getattr(self, field_name):
                label = f"workflow step {self.step_id!r} {field_name} {path!r}"
                if not isinstance(path, str):
                    raise TutorialRecordError(f"{label} must be a str, not {type(path).__name__}")
                if "{" in path or "}" in path:
                    raise TutorialRecordError(f"{label} must not contain '{{' or '}}': placeholders are not supported")
                try:
                    parts = _check_case_relative("the path", path).parts
                except ValueError as exc:
                    raise TutorialRecordError(f"{label} must be case-relative: {exc}") from exc
                if not parts:
                    raise TutorialRecordError(f"{label} must name a path inside the case, not the case root")

        formatted: set[str] = set()
        plain: set[str] = set()
        for path in self.produces:
            if isinstance(path, ProducedPath):
                if path in formatted or path in plain:
                    raise TutorialRecordError(
                        f"workflow step {self.step_id!r} produces {str(path)!r} more than once with a format; a path has one format"
                    )
                formatted.add(str(path))
            else:
                if path in formatted:
                    raise TutorialRecordError(
                        f"workflow step {self.step_id!r} produces {path!r} more than once with a format; a path has one format"
                    )
                plain.add(path)
        for path in self.consumes:
            if isinstance(path, ProducedPath):
                raise TutorialRecordError(
                    f"workflow step {self.step_id!r} consumes {str(path)!r} with a format; a format belongs on the step that produces the file"
                )

    def argv(self, contributed: Sequence[str] = ()) -> tuple[str, ...]:
        """The command line this step runs, given the arguments an axis
        contributes to it (:class:`DefaultArgument` states the rule).

        Refuses, by name, a contribution holding a default's key more than
        once."""
        contributed = tuple(contributed)
        kept: list[str] = []
        for default in self.default_arguments:
            count = len(_token_runs(contributed, default.key))
            if count > 1:
                raise TutorialRecordError(
                    f"workflow step {self.step_id!r}: the contributed arguments {list(contributed)!r} pass "
                    f"default argument key {list(default.key)!r} {count} times; pass it once to replace the default"
                )
            if count == 0:
                kept.extend(default.tokens())
        return self.command + tuple(kept) + contributed

    def produced_format(self, path: str) -> str:
        """The declared format of one of this step's ``produces`` paths."""
        for entry in self.produces:
            if entry == path:
                return entry.format if isinstance(entry, ProducedPath) else PLAIN_FILE_FORMAT
        raise TutorialRecordError(
            f"workflow step {self.step_id!r} does not produce {path!r}; it produces {[str(p) for p in self.produces]}"
        )


@dataclass(frozen=True)
class TutorialRecord:
    """A tutorial as inert data: where its native case lives, what may vary.

    Not a factory (``runtime.registry``'s ``spec_factories``): resolving a
    record calls no plugin code at all, until an axis it names actually
    runs (design §3).

    ``native_case_relpath`` is relative to the environment's own cases root
    -- there is no ambient cases root to discover (``future/
    ENVIRONMENT_CONTRACT.md`` §12, "supplied versus discovered"), so
    resolving this to an absolute path is the caller's job, not this
    dataclass's.

    ``axes`` are the record's own axes, each an :class:`AxisContract` named
    by its own ``name``. A bare study name resolves against these and
    nothing else (design §5, "an axis the record does not allow"), so one
    name can mean different things in two records. **Corrected 2026-09-26
    (record-scoped axes):** this was ``allowed_axes``, a set of names looked
    up in one stack-wide ``get_axis_catalog`` map. Two records defining
    ``dimension`` differently then shared whichever registered last:
    ``manufacturedBidomain``'s, which also writes
    ``bidomainSolverCoeffs.dimension``, silently became
    ``manufacturedEikonalECG``'s, which does not. Two axes of one record
    sharing a name are refused by name here, at load, and so is a
    ``name -> contract`` mapping, whose keys would restate each contract's
    ``name`` and could silently drop a duplicate.

    ``workflow_steps`` are keyed by ``step_id``, for ``workflow_variants``
    and for axes that contribute command arguments to a named step.
    ``workflow_variants`` maps a selector value (e.g. an adapter's choice
    between two mesh-generation routes) to the ordered tuple of step ids
    that variant runs; a record with one route leaves this empty.

    ``default_variant`` names the variant a study runs when it does not name
    the record's ``variant_selector`` (owner Q2, 2026-09-26): the route the
    native case itself runs -- "the native case is the default", applied to
    routes. A record that declares ``workflow_variants`` must declare it,
    and it must be one of them, compared exactly (no ``str()`` coercion, as
    for a study's own selector value); a ``default_variant`` on a record with
    no variants is refused too. Each refusal names the record and the
    declared variants. Core never knows what a route means; the record says
    which one is native.

    ``variant_constraints`` maps a variant to the study values it admits:
    ``{variant: {study_name: (value, ...)}}``. When that variant runs --
    named by the study or taken as the default -- a study that sets
    ``study_name`` must set it to one of the listed values, compared
    strictly (``_strictly_equal``: ``True`` is not ``1``); leaving it unset
    is always admitted. Any other value is refused by name before anything is
    written (``check_variant_constraints``). A route that can build only one
    shape of case cannot honour a study value that asks for another; without
    this, the value would be written into documents the route's steps then
    contradict, or silently have no effect. Added 2026-09-26 (review 54b
    I3). ``study_name`` is an axis the record declares or a
    ``document:dotted.path`` key, never the selector itself, and each is
    checked at construction, by name.
    """

    name: str
    native_case_relpath: str
    workflow_steps: tuple[WorkflowStep, ...]
    #: Data a step reads that is not in the native case folder (design
    #: §2.1): each input's destinations are excluded from the native-case
    #: copy at staging time and overlaid from wherever it resolves to
    #: (``resolve_record_inputs``, ``record_execution._stage``).
    inputs: tuple[RecordInput, ...] = ()
    axes: tuple[AxisContract, ...] = ()
    workflow_variants: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The reserved study name that selects among ``workflow_variants`` --
    #: DECLARED BY THE RECORD (item 4's vocabulary fix), never a name core
    #: invents. Core used to reserve the literal name ``"mesh"``
    #: (``MESH_SELECTOR_NAME``, deleted) for every record alike, which is
    #: itself solver vocabulary core has no business naming; a record that
    #: declares ``workflow_variants`` must now declare its own selector name
    #: (cardiacFOAM's records declare ``"mesh"`` themselves, step 4).
    #: ``None`` when the record declares no variants to select among.
    variant_selector: str | None = None
    #: The ``workflow_variants`` key a study that names no route runs (owner
    #: Q2, 2026-09-26; see the class docstring). ``None`` exactly when the
    #: record declares no variants.
    default_variant: str | None = None
    #: Per variant, the values each constrained study name admits (see the
    #: class docstring). Added 2026-09-26 (review 54b I3).
    variant_constraints: Mapping[str, Mapping[str, tuple[Any, ...]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise TutorialRecordError("a tutorial record must have a non-empty name")
        if not self.native_case_relpath:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} must declare a native_case_relpath"
            )
        # Case-relative, like every other case-addressing string this module
        # checks (a patch's document, a study name's document) -- a record's
        # native case lives under the environment's cases root, never at an
        # absolute path or one that escapes it (minor m4).
        _check_case_relative(
            f"tutorial record {self.name!r}'s native_case_relpath",
            self.native_case_relpath,
        )
        if isinstance(self.axes, (Mapping, AxisContract, str)):
            raise TutorialRecordError(
                f"tutorial record {self.name!r} axes must be a sequence of AxisContract, "
                f"not {type(self.axes).__name__}; each contract already carries its own name"
            )
        object.__setattr__(self, "axes", tuple(self.axes))
        seen: set[str] = set()
        for axis in self.axes:
            if not isinstance(axis, AxisContract):
                raise TutorialRecordError(
                    f"tutorial record {self.name!r} axes holds {axis!r}, which is not an AxisContract"
                )
            if axis.name in seen:
                raise TutorialRecordError(
                    f"tutorial record {self.name!r} declares axis {axis.name!r} twice; "
                    "a study name must resolve to one axis in its record"
                )
            seen.add(axis.name)
        if PARALLEL_STUDY_NAME in seen or self.variant_selector == PARALLEL_STUDY_NAME:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} names an axis or its variant "
                f"selector {PARALLEL_STUDY_NAME!r}; {PARALLEL_STUDY_NAME!r} is reserved "
                "for how a run executes (serial or parallel), never case content"
            )
        object.__setattr__(self, "workflow_steps", tuple(self.workflow_steps))
        step_ids = [step.step_id for step in self.workflow_steps]
        if len(set(step_ids)) != len(step_ids):
            raise TutorialRecordError(
                f"tutorial record {self.name!r} declares duplicate workflow "
                f"step ids: {step_ids}"
            )
        known_steps = frozenset(step_ids)
        object.__setattr__(self, "inputs", tuple(self.inputs))
        self._check_inputs()
        variants = {
            selector: tuple(steps)
            for selector, steps in dict(self.workflow_variants).items()
        }
        for selector, steps in variants.items():
            unknown = [step for step in steps if step not in known_steps]
            if unknown:
                raise TutorialRecordError(
                    f"tutorial record {self.name!r}'s workflow_variants "
                    f"{selector!r} names undeclared step id(s) {unknown}"
                )
        object.__setattr__(self, "workflow_variants", variants)
        if variants and not self.variant_selector:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} declares workflow_variants "
                f"{sorted(variants)} but no variant_selector name to select "
                "among them"
            )
        if variants and self.default_variant is None:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} declares workflow_variants "
                f"{sorted(variants)} but no default_variant naming the one "
                "its native case runs"
            )
        if self.default_variant is not None:
            if not variants:
                raise TutorialRecordError(
                    f"tutorial record {self.name!r} declares default_variant "
                    f"{self.default_variant!r} but no workflow_variants"
                )
            if not any(_strictly_equal(self.default_variant, key) for key in variants):
                raise TutorialRecordError(
                    f"tutorial record {self.name!r}'s default_variant "
                    f"{self.default_variant!r} is not one of its declared "
                    f"workflow_variants ({sorted(variants)})"
                )
        object.__setattr__(self, "variant_constraints", self._checked_variant_constraints(variants))

    def _checked_variant_constraints(
        self, variants: Mapping[str, tuple[str, ...]],
    ) -> dict[str, dict[str, tuple[Any, ...]]]:
        label = f"tutorial record {self.name!r}'s variant_constraints"
        if not isinstance(self.variant_constraints, Mapping):
            raise TutorialRecordError(
                f"{label} must be a mapping of variant -> {{study name: values}}, "
                f"not {type(self.variant_constraints).__name__}"
            )
        checked: dict[str, dict[str, tuple[Any, ...]]] = {}
        for variant, constraints in self.variant_constraints.items():
            if not any(_strictly_equal(variant, key) for key in variants):
                raise TutorialRecordError(
                    f"{label} name {variant!r}, which is not one of its declared "
                    f"workflow_variants ({sorted(variants)})"
                )
            if not isinstance(constraints, Mapping):
                raise TutorialRecordError(
                    f"{label} for {variant!r} must be a mapping of study name -> values, "
                    f"not {type(constraints).__name__}"
                )
            checked[variant] = {}
            for name, allowed in constraints.items():
                if name == self.variant_selector:
                    raise TutorialRecordError(
                        f"{label} for {variant!r} constrain the selector {name!r} itself; "
                        "the selector chooses the variant and cannot be constrained by it"
                    )
                try:
                    sort_study_name(name, axes=self.axes)
                except TutorialRecordError as exc:
                    raise TutorialRecordError(
                        f"{label} for {variant!r} name {name!r}, which is not a study name "
                        f"this record resolves: {exc}"
                    ) from exc
                if isinstance(allowed, str):
                    raise TutorialRecordError(
                        f"{label} for {variant!r}: {name!r} admits the bare string {allowed!r}; "
                        "give a sequence of admitted values"
                    )
                if not isinstance(allowed, Sequence):
                    raise TutorialRecordError(
                        f"{label} for {variant!r}: {name!r} must admit a sequence of values, "
                        f"not {type(allowed).__name__}"
                    )
                if not allowed:
                    raise TutorialRecordError(
                        f"{label} for {variant!r}: {name!r} admits no value; a name no "
                        "value may take is a study name the variant cannot run with at all"
                    )
                checked[variant][name] = tuple(allowed)
        return checked

    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.workflow_steps)

    def axis_names(self) -> tuple[str, ...]:
        return tuple(axis.name for axis in self.axes)

    def _check_inputs(self) -> None:
        """Design §2.1's remaining refusals: the ones only the record, not a
        lone :class:`RecordInput`, can check -- they read ``workflow_steps``."""
        seen_names: set[str] = set()
        seen_destinations: dict[str, str] = {}
        for input_ in self.inputs:
            if not isinstance(input_, RecordInput):
                raise TutorialRecordError(
                    f"tutorial record {self.name!r} inputs holds {input_!r}, which is not a RecordInput"
                )
            if input_.name in seen_names:
                raise TutorialRecordError(
                    f"tutorial record {self.name!r} declares input {input_.name!r} twice"
                )
            seen_names.add(input_.name)
            for destination in input_.destinations():
                for other_destination, other_input in seen_destinations.items():
                    if destination == other_destination:
                        raise TutorialRecordError(
                            f"tutorial record {self.name!r}: input {input_.name!r} and "
                            f"{other_input!r} both write destination {destination!r}"
                        )
                    first, second = sorted((destination, other_destination), key=len)
                    if PurePosixPath(second) == PurePosixPath(first) or PurePosixPath(first) in PurePosixPath(second).parents:
                        raise TutorialRecordError(
                            f"tutorial record {self.name!r}: input {input_.name!r}'s destination "
                            f"{destination!r} and {other_input!r}'s {other_destination!r} overlap"
                        )
                seen_destinations[destination] = input_.name
                if not _any_step_consumes(destination, self.workflow_steps):
                    raise TutorialRecordError(
                        f"tutorial record {self.name!r}: input {input_.name!r}'s destination "
                        f"{destination!r} is not consumed by any workflow step; a supplied file "
                        "must be tied to a step so provenance covers it"
                    )
                touch = _first_touching_step(destination, self.workflow_steps)
                if touch is not None and touch[1] == "produces":
                    raise TutorialRecordError(
                        f"tutorial record {self.name!r}: input {input_.name!r}'s destination "
                        f"{destination!r} is produced by step "
                        f"{self.workflow_steps[touch[0]].step_id!r} before any step consumes it; "
                        "that path would be generated, not supplied"
                    )


# ---------------------------------------------------------------------------
# The axis contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AxisPatch:
    """One value an axis (or a direct study key) proposes to write.

    Deliberately its own type, not ``case_write.ParameterAssignment``: an
    axis is pure and knows nothing about ``owner``/``workflow``/bindings --
    only a document, a key path, and a value. ``patches_to_parameters``
    promotes a merged, conflict-checked set of these into real
    ``ParameterAssignment``s.

    **No ``validated`` field here (review finding M2).** Whether a patch is
    validated is not this patch's own opinion to state -- an axis is not the
    record-key catalog, and a self-reported ``validated=True`` default let an
    axis-produced patch for a key absent from any catalog reach a commit
    unchecked (M3's defect). ``resolve_case_patches`` now runs EVERY patch,
    axis-produced or a direct study key alike, through
    ``RecordKeyValidationCapability.validate`` and carries the answer on
    ``SourcedPatch.validated`` instead -- the validator decides, never the
    patch.
    """

    document: str
    key_path: tuple[str, ...]
    value: Any
    value_kind: str

    def __post_init__(self) -> None:
        _check_case_relative("a patch's document", self.document)
        object.__setattr__(self, "key_path", tuple(self.key_path))
        if not self.key_path:
            raise TutorialRecordError(
                f"a patch on {self.document!r} names no key"
            )

    def slot(self) -> str:
        """The address this patch occupies, document scope included."""
        return f"{self.document}::{'.'.join(self.key_path)}"


@dataclass(frozen=True)
class AxisResult:
    """One axis's pure output: the patches it derives, and any command
    arguments it contributes to named workflow steps.

    A contribution that passes one of the step's default-argument keys
    replaces that default; anything else is appended (:class:`DefaultArgument`,
    owner Q3, 2026-09-26).
    """

    patches: tuple[AxisPatch, ...] = ()
    command_arguments: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "patches", tuple(self.patches))
        object.__setattr__(
            self,
            "command_arguments",
            {step: tuple(args) for step, args in dict(self.command_arguments).items()},
        )


#: An axis's resolution function: the study value, and a read-only view of
#: the staged case (its root -- an axis reads through it, e.g. an existing
#: mesh-description file's extents, and must not write it; nothing here
#: enforces that mechanically, see the design's §5 static-gate note).
AxisFunction = Callable[[Any, Path], AxisResult]


@dataclass(frozen=True)
class AxisContract:
    """A named axis: what value it accepts, and the pure function computing
    its patches and command arguments.

    Core defines this contract and ships no axis of its own (design §3:
    "Core defines the contract and ships no solver axes"). An adapter
    declares each axis on the record that uses it (``TutorialRecord.axes``).
    Corrected 2026-09-26 (record-scoped axes): an adapter used to provide
    axes stack-wide through ``AxisCapability``/``get_axis_catalog``, both
    deleted.
    """

    name: str
    value_kind: str
    resolve: AxisFunction

    def __post_init__(self) -> None:
        if not self.name:
            raise TutorialRecordError("an axis must have a non-empty name")
        if not callable(self.resolve):
            raise TutorialRecordError(f"axis {self.name!r}'s resolve must be callable")


# ---------------------------------------------------------------------------
# Selectors (item 4): a reserved study name that picks among a record's
# declared `workflow_variants` rather than naming a document key or an axis.
# A selector produces no patches at all -- it only chooses which of the
# record's own declared workflow steps run for this case.
# ---------------------------------------------------------------------------

#: Core defines the SELECTOR MECHANISM only, no selector name of its own
#: (item 4's vocabulary fix, 2026-09-24): a literal core-owned
#: ``MESH_SELECTOR_NAME = "mesh"`` used to be reserved for every record
#: alike, which is itself solver vocabulary core has no business naming.
#: Each record now declares its OWN reserved name via
#: ``TutorialRecord.variant_selector`` -- cardiacFOAM's records declare
#: ``"mesh"`` themselves (step 4). `dimension` is a cardiac AXIS in the
#: design (docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
#: design.md §3), not a selector, and stays adapter-owned either way.


def resolve_variant_selector(record: TutorialRecord, value: Any) -> tuple[str, ...]:
    """Resolve the record's own declared ``variant_selector`` name to one
    variant's step ids.

    A selector, not an axis (item 4): it produces no :class:`AxisPatch` at
    all, only which of ``record.workflow_variants`` runs for this case.
    Refused BY NAME when the record declares no variants to select among,
    when ``value`` is ``None`` (a null selector value is never a valid
    choice), or when ``value`` does not name a declared variant EXACTLY --
    no ``str()`` coercion: an integer ``1`` must not silently match a
    variant literally named ``"1"``, nor ``True`` one named ``"True"``.
    """
    if not record.workflow_variants:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} declares no workflow_variants; "
            f"{record.variant_selector!r} selects among variants and has "
            "nothing to select"
        )
    if value is None:
        raise TutorialRecordError(
            f"{record.variant_selector!r} was given a null value; it must "
            f"name one of tutorial record {record.name!r}'s declared "
            f"variants ({sorted(record.workflow_variants)})"
        )
    if value not in record.workflow_variants:
        raise TutorialRecordError(
            f"{value!r} is not a workflow variant tutorial record "
            f"{record.name!r} declares (declared variants: "
            f"{sorted(record.workflow_variants)})"
        )
    return record.workflow_variants[value]


def check_variant_constraints(
    record: TutorialRecord, variant: str,
    study_by_source: Mapping[str, Mapping[str, Any]],
) -> None:
    """Refuse, by name, a study value the running ``variant`` does not admit
    (``TutorialRecord.variant_constraints``; review 54b I3, 2026-09-26).

    Every source is checked, so the refusal names the source that set the
    value. A name the study leaves unset is always admitted."""
    constraints = record.variant_constraints.get(variant, {})
    for source, values in study_by_source.items():
        for name, allowed in constraints.items():
            if name not in values:
                continue
            value = values[name]
            if not any(_strictly_equal(value, admitted) for admitted in allowed):
                raise TutorialRecordError(
                    f"tutorial record {record.name!r}'s workflow variant {variant!r} admits "
                    f"{name!r} only as one of {list(allowed)!r}, or unset; {source!r} sets it "
                    f"to {value!r}"
                )


# ---------------------------------------------------------------------------
# Study name sorting (design §3, §4 step 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentKeyName:
    """A ``document:dotted.path`` study name: a literal dictionary key."""

    document: str
    key_path: tuple[str, ...]


@dataclass(frozen=True)
class AxisMatch:
    """A bare study name that resolved to an allowed, provided axis."""

    axis: AxisContract


def sort_study_name(
    name: str,
    *,
    axes: Sequence[AxisContract],
) -> DocumentKeyName | AxisMatch:
    """Classify one study name, refusing by name before anything runs.

    A name containing ``:`` is a ``document:dotted.path`` literal key (design
    §3): the document is the substring before the FIRST colon (itself may
    contain ``/``, e.g. ``constant/someProperties``), the rest is a
    dot-joined key path. Its document is checked for shape only (case-
    relative, no ``..`` escape, non-empty) -- whether the key itself is one a
    real catalog recognises is adapter work, resolved later by
    ``RecordKeyValidationCapability`` (``resolve_case_patches``), not here.

    A name with no colon is a bare axis name, resolved against ``axes``, the
    entry's own (``TutorialRecord.axes``), and refused when none of them has
    that name. Corrected 2026-09-26 (record-scoped axes): this took a
    record's allowed names and the stack-wide axis catalog, and refused an
    allowed name no adapter provided and a provided name the record did not
    allow; with axes on the record, neither state exists.
    """
    if ":" in name:
        document, _, dotted = name.partition(":")
        if not document or not dotted:
            raise TutorialRecordError(
                f"{name!r} is not a valid 'document:dotted.path' name"
            )
        _check_case_relative(f"study name {name!r}'s document", document)
        key_path = tuple(dotted.split("."))
        if not all(key_path):
            raise TutorialRecordError(
                f"{name!r} has an empty segment in its dotted key path"
            )
        return DocumentKeyName(document=document, key_path=key_path)

    for axis in axes:
        if axis.name == name:
            return AxisMatch(axis=axis)
    raise TutorialRecordError(
        f"{name!r} is neither a 'document:dotted.path' key nor an axis "
        f"this entry declares (declared axes: {sorted(axis.name for axis in axes)})"
    )


# ---------------------------------------------------------------------------
# Combine: conflict refusal (design §4 step 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcedPatch:
    """One patch, tagged with where it came from, and how validated the
    record-key catalog considers it.

    ``validated`` lives HERE, not on ``AxisPatch`` (review finding M2): it is
    always ``RecordKeyValidationCapability.validate``'s own answer for this
    exact ``(document, key_path, value)``, computed uniformly for a direct
    study key or an axis-produced patch alike (M3) -- never a value a patch
    invented about itself. There is deliberately no default: every call site
    that builds one states an explicit answer.
    """

    patch: AxisPatch
    source: str
    validated: bool

    def slot(self) -> str:
        return self.patch.slot()


def _strictly_equal(first: Any, second: Any) -> bool:
    """Same Python type AND ``==`` (review finding M7).

    Plain ``==`` alone agrees that ``1 == True`` and ``1 == 1.0`` -- both
    real conflicts here, since they come from two DIFFERENT declared
    ``value_kind``s (an "integer" and a "boolean", or an "integer" and a
    "scalar") that only coincidentally compare equal under Python's numeric
    tower. ``combine_patches`` never reaches this on two values it already
    knows have differing kinds, but a same-kind conflict (e.g. two "integer"
    patches whose values happen to be ``1`` and ``True`` under a validator
    that mis-declares a boolean as an integer) must still be caught, so the
    type check is strict here too rather than assumed from the kind check.
    """
    return type(first) is type(second) and first == second


def combine_patches(patches: Sequence[SourcedPatch]) -> tuple[SourcedPatch, ...]:
    """Step 6, 'Combine' (design §4): one list, refusing a real conflict.

    Two sources naming the same (document, key) slot are fine when they
    agree on the value -- e.g. a study restates a base default explicitly --
    and refused, BY NAME, naming both sources, when they do not. This is the
    tutorial-record replacement for an adapter's own pre-existing override-
    merging convention's "later write wins": that older behaviour is left
    exactly as it is for old factory tutorials (design §4 step 6's own
    instruction), which never call this function.

    "Agree" is checked two ways (review finding M7), both refusing:

    - a differing ``value_kind`` is a conflict even when the raw values
      happen to compare equal (``1`` and ``1.0`` under "integer" vs
      "scalar") -- two sources cannot both be right about what KIND of
      value a slot holds while disagreeing on the kind itself;
    - same-kind values are compared with strict same-type equality
      (:func:`_strictly_equal`), not plain ``==``, so ``1`` and ``True``
      conflict rather than silently agreeing the way Python's ``1 == True``
      would suggest.
    """
    by_slot: dict[str, SourcedPatch] = {}
    for sourced in patches:
        slot = sourced.slot()
        existing = by_slot.get(slot)
        if existing is None:
            by_slot[slot] = sourced
            continue
        if existing.patch.value_kind != sourced.patch.value_kind:
            raise TutorialRecordError(
                f"{slot!r} is set to different value kinds by "
                f"{existing.source!r} ({existing.patch.value_kind!r}, "
                f"{existing.patch.value!r}) and {sourced.source!r} "
                f"({sourced.patch.value_kind!r}, {sourced.patch.value!r})"
            )
        if not _strictly_equal(existing.patch.value, sourced.patch.value):
            raise TutorialRecordError(
                f"{slot!r} is set to different values by {existing.source!r} "
                f"({existing.patch.value!r}) and {sourced.source!r} "
                f"({sourced.patch.value!r})"
            )
        # Same value from two sources: keep whichever was seen first. There
        # used to be a tie-break here preferring whichever of the two was
        # validated, on the theory that an adapter-validated agreement is
        # more informative than an unvalidated one that happens to match it.
        # That branch is dead code (item 6, 2026-09-24): every patch reaching
        # this function -- a direct key's or an axis's, alike -- was already
        # run through the SAME `direct_key_validator` for this SAME
        # (document, key_path, value) by `resolve_case_patches` (M3), so two
        # SourcedPatch values that pass the equality check directly above
        # always carry the SAME `validated` answer too; there is no
        # "exactly one of the two is validated" case left for the branch to
        # catch. See test_combine_patches_keeps_the_first_agreeing_patch_
        # regardless_of_validated_flag, which proves the removal by feeding
        # combine_patches a hand-built pair (impossible via the real
        # pipeline) and confirming the second, validated one is NOT promoted.
    return tuple(by_slot.values())


# ---------------------------------------------------------------------------
# Resolving one case's whole study (design §4 steps 4-6)
# ---------------------------------------------------------------------------


def _case_root_digest(case_root: Path) -> str:
    """A content digest over every file's path AND bytes under ``case_root``
    -- the read-only invariant an axis's ``resolve`` must never break
    (review finding M2, "axis purity enforced at runtime").

    Reuses ``case_write._digest_bytes`` for each file's own digest (the same
    helper a rendered file's ``content_digest`` already uses), then combines
    every (relative path, digest) pair, sorted for determinism, into one
    digest over the whole tree -- the design's own axis contract already
    documents this as an invariant nothing mechanically enforced; this is
    that enforcement.
    """
    import hashlib

    from .case_write import _digest_bytes

    entries = []
    if case_root.is_dir():
        for path in sorted(case_root.rglob("*")):
            if path.is_file():
                relpath = path.relative_to(case_root).as_posix()
                entries.append(f"{relpath}:{_digest_bytes(path.read_bytes())}")
    encoded = "\n".join(entries).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


DirectKeyValidator = Callable[[str, tuple[str, ...], Any], tuple[str, bool]]


def _validate_or_wrap(
    direct_key_validator: DirectKeyValidator,
    document: str,
    key_path: tuple[str, ...],
    value: Any,
) -> tuple[str, bool]:
    """Call ``direct_key_validator``, wrapping any exception it raises in a
    ``TutorialRecordError`` naming the document and key (minor m6).

    An adapter's validator may raise anything -- a deliberate ``KeyError``
    for an unrecognised key, or an unrelated bug -- and its own message may
    not mention which key was being checked at all. This function is the one
    place that always knows, so it names it, regardless of what the
    validator itself said (the original exception is chained via ``from``,
    never discarded).
    """
    try:
        return direct_key_validator(document, key_path, value)
    except Exception as exc:
        dotted = ".".join(key_path)
        raise TutorialRecordError(
            f"validating {document}:{dotted} raised {type(exc).__name__}: {exc}"
        ) from exc


def resolve_case_patches(
    record: TutorialRecord,
    *,
    study_by_source: Mapping[str, Mapping[str, Any]],
    staged_case_root: Path,
    direct_key_validator: DirectKeyValidator,
) -> tuple[tuple[SourcedPatch, ...], dict[str, tuple[str, ...]]]:
    """Resolve one case's whole study into a conflict-checked patch list.

    ``study_by_source`` maps a source label (e.g. ``"base"``, ``"sweep"``) to
    that source's flat ``name -> value`` mapping -- the design's "base" and
    the sweep's resolved axis values (design §4's worked example). Every name
    across every source is SORTED FIRST (design §4 step 4, "refused by name
    before anything runs"): this function classifies every name before
    running a single axis, so a bad name anywhere in the study is refused
    before any axis has a side-effect-free chance to run either.

    Every DIRECT key is then validated, in full, BEFORE any axis runs (minor
    m2): a study whose direct keys include one the catalog will refuse must
    never let a well-formed, allowed axis run first and have its (pure, but
    still real) resolution wasted, or worse, its command arguments collected
    into a result that is about to be thrown away anyway. Only once every
    direct key has passed does the first axis run.

    Every patch -- a direct key's OR an axis's OUTPUT -- then goes through
    the SAME ``direct_key_validator`` (review finding M3): an axis is not a
    back door around the record-key catalog. ``AxisPatch`` carries no
    ``validated`` opinion of its own (M2); the validator's answer becomes
    each patch's ``SourcedPatch.validated``.

    Returns ``(combined_patches, command_arguments_by_step)`` -- the latter
    is every axis's ``AxisResult.command_arguments``, merged by step id in
    axis-resolution order (design's "workflow steps with axis-provided
    command arguments").
    """
    classified: list[tuple[str, str, DocumentKeyName | AxisMatch, Any]] = []
    for source, values in study_by_source.items():
        for name, value in values.items():
            sorted_name = sort_study_name(name, axes=record.axes)
            classified.append((source, name, sorted_name, value))

    direct_entries = [
        entry for entry in classified if isinstance(entry[2], DocumentKeyName)
    ]
    axis_entries = [
        entry for entry in classified if isinstance(entry[2], AxisMatch)
    ]

    sourced_patches: list[SourcedPatch] = []
    for source, _name, sorted_name, value in direct_entries:
        value_kind, validated = _validate_or_wrap(
            direct_key_validator, sorted_name.document, sorted_name.key_path, value,
        )
        patch = AxisPatch(
            document=sorted_name.document, key_path=sorted_name.key_path,
            value=value, value_kind=value_kind,
        )
        sourced_patches.append(SourcedPatch(patch=patch, source=source, validated=validated))

    known_step_ids = frozenset(record.step_ids())
    steps_by_id = {step.step_id: step for step in record.workflow_steps}
    command_arguments: dict[str, tuple[str, ...]] = {}
    command_argument_source: dict[str, str] = {}
    for source, name, sorted_name, value in axis_entries:
        del source  # an axis patch is sourced by the axis's own name, below
        axis = sorted_name.axis
        # Minor: the axis's OWN declared value_kind is checked against the
        # study's value BEFORE resolve ever runs -- an axis's `resolve` is
        # arbitrary adapter code, and a value that does not fit the shape
        # the axis itself declares (e.g. a non-integer string for an
        # "integer" axis) used to reach that code unchecked, surfacing as
        # whatever native exception the adapter's own coercion happened to
        # raise (a bare ValueError naming neither the axis nor the study).
        value_kind_reasons = validate_value_shape(axis.value_kind, value)
        if value_kind_reasons:
            raise TutorialRecordError(
                f"axis {name!r} declares value_kind {axis.value_kind!r}, "
                f"but the value {value!r} does not fit it: "
                f"{'; '.join(value_kind_reasons)}"
            )
        # M2: axis purity enforced at runtime, not merely documented. An
        # axis's own contract (AxisFunction's docstring) says it reads the
        # staged case and must not write it -- nothing mechanically enforced
        # that before this, so a misbehaving axis (or one that imports a
        # writer by mistake) could mutate the staged case directly, outside
        # the one commit_case_write channel, and nothing here would notice.
        before_digest = _case_root_digest(staged_case_root)
        result = axis.resolve(value, staged_case_root)
        after_digest = _case_root_digest(staged_case_root)
        if after_digest != before_digest:
            raise TutorialRecordError(
                f"axis {name!r} is not pure: it modified the staged case "
                "while resolving. An axis may only READ the staged case "
                "and return patches/command arguments; only "
                "commit_case_write may write a case."
            )
        for patch in result.patches:
            value_kind, validated = _validate_or_wrap(
                direct_key_validator, patch.document, patch.key_path, patch.value,
            )
            revalidated = AxisPatch(
                document=patch.document, key_path=patch.key_path,
                value=patch.value, value_kind=value_kind,
            )
            sourced_patches.append(
                SourcedPatch(patch=revalidated, source=name, validated=validated)
            )
        for step_id, extra_args in result.command_arguments.items():
            # M6, first rule: a step id the record does not declare in its
            # own `workflow_steps` is refused by name -- an axis contributing
            # arguments to a step that will never run (or never existed) is
            # a defect, not a no-op.
            if step_id not in known_step_ids:
                raise TutorialRecordError(
                    f"axis {name!r} contributes command arguments to step "
                    f"{step_id!r}, which tutorial record {record.name!r} "
                    f"does not declare (declared steps: {sorted(known_step_ids)})"
                )
            extra_args = tuple(extra_args)
            # Owner Q3 (2026-09-26): the contribution must name each of the
            # step's default-argument keys at most once
            # (`DefaultArgument`'s rule), refused here, before any later
            # axis runs, rather than when the DAG is built.
            try:
                steps_by_id[step_id].argv(extra_args)
            except TutorialRecordError as exc:
                raise TutorialRecordError(f"axis {name!r}: {exc}") from exc
            existing_args = command_arguments.get(step_id)
            if existing_args is None:
                command_arguments[step_id] = extra_args
                command_argument_source[step_id] = name
                continue
            # M6, second rule: two axes contributing to the SAME step is
            # fine when they agree byte-for-byte, and refused BY NAME
            # (naming both axes and the step) otherwise -- no concatenation,
            # no later-wins. An agreeing second axis contributes nothing
            # further; the arguments are not duplicated either.
            if existing_args != extra_args:
                raise TutorialRecordError(
                    f"step {step_id!r} receives conflicting command arguments "
                    f"from axis {command_argument_source[step_id]!r} "
                    f"({list(existing_args)}) and axis {name!r} ({list(extra_args)})"
                )

    combined = combine_patches(sourced_patches)
    return combined, dict(command_arguments)


# ---------------------------------------------------------------------------
# Unchanged detection (design §4 step 7)
# ---------------------------------------------------------------------------


def split_unchanged(
    patches: Sequence[SourcedPatch],
    *,
    case_root: Path,
    read_current_value: Callable[[Path, str], Any] | None,
    values_agree: Callable[[str, Any, Any], bool] | None,
) -> tuple[tuple[SourcedPatch, ...], tuple[SourcedPatch, ...]]:
    """Split ``patches`` into ``(to_write, unchanged)`` (design §4 step 7).

    Uses the adapter's own typed comparison (``values_agree``, sourced from
    ``CaseValueComparisonCapability``) against the staged case's current
    value (``read_current_value``, sourced from ``ConfigValueCapability``) --
    never Python ``==``/string equality (see ``CaseValueComparisonCapability``'s
    docstring for why). ``read_current_value`` is always called with the
    patch's ``key_path`` AS A TUPLE (``patch.key_path`` itself, never a
    dotted string): a real adapter's reader may split that tuple into a
    scope and a leaf key of its own file format's shape (review finding B1)
    -- this function does not know, or need to know, how any adapter's
    reader turns a key path into a scope.

    When there is no reader or no comparator, every patch is reported
    CHANGED, never silently dropped: an "unchanged" claim this function
    cannot back is not made. When a reader or comparator IS present but
    raises for a particular patch, that exception propagates -- it is not
    caught and reinterpreted as "changed" here.
    """
    if read_current_value is None or values_agree is None:
        return tuple(patches), ()
    to_write: list[SourcedPatch] = []
    unchanged: list[SourcedPatch] = []
    for sourced in patches:
        patch = sourced.patch
        document_path = Path(case_root) / patch.document
        current = read_current_value(document_path, patch.key_path)
        if current is not None and values_agree(patch.value_kind, patch.value, current):
            unchanged.append(sourced)
        else:
            to_write.append(sourced)
    return tuple(to_write), tuple(unchanged)


# ---------------------------------------------------------------------------
# Promoting to the real write channel (design §4 step 7's commit)
# ---------------------------------------------------------------------------


def patches_to_parameters(
    patches: Sequence[SourcedPatch],
    *,
    owner: str,
) -> tuple[Any, ...]:
    """Promote a merged, conflict-checked patch list into real
    ``case_write.ParameterAssignment`` values, ready for one
    ``CaseMutationRequest`` (design §4 step 7: "everything goes in one
    commit_case_write").

    ``source="case"`` for every assignment: each one is a genuine per-case
    choice (a direct study key, or an axis's derived value), the same
    reasoning an adapter's own override-resolution path uses for its own
    ``source="case"`` assignments.
    """
    from .case_write import ParameterAssignment

    return tuple(
        ParameterAssignment(
            qualified_id=sourced.slot(),
            owner=owner,
            document=sourced.patch.document,
            key_path=sourced.patch.key_path,
            binding={},
            value=sourced.patch.value,
            value_kind=sourced.patch.value_kind,
            source="case",
            validated=sourced.validated,
        )
        for sourced in patches
    )


# ---------------------------------------------------------------------------
# Building a plugin's own record catalog (a plain {record.name: record} dict
# comprehension silently drops a duplicate name -- the same hazard
# record-scoped axes closed for two axes sharing a name within one record,
# 2026-09-26; this closes it for two records sharing a name across a
# plugin's own TUTORIAL_RECORDS).
# ---------------------------------------------------------------------------


def record_input_destinations(record: "TutorialRecord") -> frozenset[str]:
    """Every case-relative destination any of ``record``'s inputs writes --
    never taken from the native case folder at staging time (design §2.3),
    the same exclusion role ``record_execution.record_generated_relpaths``
    plays for a step's own outputs."""
    return frozenset(destination for input_ in record.inputs for destination in input_.destinations())


def build_tutorial_record_catalog(
    records: Sequence[TutorialRecord],
) -> dict[str, TutorialRecord]:
    """Build a ``name -> record`` catalog, refusing a duplicate name by name.

    A plugin's own ``TUTORIAL_RECORDS`` module constant is exactly this: a
    tuple of the records it registers, reduced to a dict keyed by
    ``TutorialRecord.name``. Writing that reduction as a dict comprehension
    lets a second record with the same name silently overwrite the first,
    with no error and no trace of which record was actually reachable --
    the same hazard ``TutorialRecord.__post_init__`` already refuses for two
    axes sharing a name inside one record. Neutral (core owns no record
    vocabulary; this is just "how to build the dict without losing one"), so
    both ``cardiacfoam.records`` and ``opencarp.records`` share it.
    """
    catalog: dict[str, TutorialRecord] = {}
    for record in records:
        if record.name in catalog:
            raise TutorialRecordError(
                f"duplicate tutorial record name {record.name!r}: both "
                f"{catalog[record.name].native_case_relpath!r} and "
                f"{record.native_case_relpath!r} claim it; a record catalog "
                "requires unique names"
            )
        catalog[record.name] = record
    return catalog
