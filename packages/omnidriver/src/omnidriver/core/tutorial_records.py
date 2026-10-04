"""A tutorial record: inert data, and the axis contract it draws on.

Everything here runs against a staged clone and stops at proposing patches; `patches_to_parameters` is the one seam to `case_write`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from .case_write import _check_case_relative
from .contracts.dictionary import validate_value_shape

if TYPE_CHECKING:
    from .conformance_study import ConformanceStudy


class TutorialRecordError(ValueError):
    """A tutorial-record study refused a name, a conflict, or a missing case; the message names the offending key or source."""


# ---------------------------------------------------------------------------
# The record itself
# ---------------------------------------------------------------------------


PARALLEL_STUDY_NAME = "parallel"
"""The one study name core reserves for how a record case runs. Absent or
``False``: serial, the native default. Any other
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

    A ``str`` equal to the path, so every reader of ``WorkflowStep.produces``
    sees plain paths. The format rides on ``artifact_format`` and is read only
    through :meth:`WorkflowStep.produced_format`: a string operation returns a
    plain ``str`` without it, and entries compare equal by path alone. Core
    never interprets the format; it names the reader a plugin returns from
    ``get_artifact_value_reader``.
    """

    artifact_format: str

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
        entry.__dict__["artifact_format"] = format
        return entry

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"ProducedPath is immutable; cannot set {name!r}")

    def __reduce__(self):
        return (ProducedPath, (str(self), self.artifact_format))

    def __repr__(self) -> str:
        return f"ProducedPath({str(self)!r}, format={self.artifact_format!r})"


def _token_runs(tokens: Sequence[str], key: Sequence[str]) -> list[int]:
    """Every index where ``key`` occurs in ``tokens`` as a contiguous run (overlapping runs counted)."""
    width = len(key)
    key = tuple(key)
    return [i for i in range(len(tokens) - width + 1) if tuple(tokens[i:i + width]) == key]


def _first_touching_step(
    path_str: str, steps: Sequence["WorkflowStep"],
) -> tuple[int, str] | None:
    """The first step touching ``path_str``, exactly or as a parent or child directory, and whether through ``consumes`` or ``produces``."""
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
    """An argument a workflow step passes unless an axis passes its own.

    On the command line it is ``key`` followed by ``values``:
    ``key=("-setnumber", "lc"), values=("0.1",)`` passes ``-setnumber lc 0.1``.
    ``key`` is as many tokens as name the argument; core compares tokens for
    equality and parses no flag.

    An axis replaces a default by passing its ``key`` tokens contiguously in
    its ``AxisResult.command_arguments`` for that step: the default's tokens
    are dropped and the contribution appended. An axis that does not pass the
    key appends, and the default stays. What follows the key is passed as
    given; the record declares only the default, never the values that may
    replace it.

    Ambiguity is refused by name. At construction each default's ``key`` must
    occur exactly once as a contiguous run in the step's default command line
    (``command`` plus every default's tokens): that refuses a key the command
    already holds, two defaults with one key, and a key inside another
    default's tokens. At resolution (``WorkflowStep.argv``) a contribution
    holding one key more than once is refused.
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
    """Case-relative shape, no ``{``/``}``, and never the root: the refusals a ``produces``/``consumes`` path gets."""
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
    """Data a record's steps read but that is not in its native case folder:
    a patient anatomy bundle, a shared mesh, a 1D graph.

    ``files`` is a tuple of ``(path inside the input, case-relative
    destination)`` pairs; ``(".", destination)`` takes the input's own root,
    which may itself be a file. ``native_relpath`` is the input's default
    location under the environment's cases root; ``None`` means it has no
    ambient location and must be supplied (``--input NAME=PATH``).

    Destination conflicts with each other or with a step's consumes/produces
    are checked on the owning :class:`TutorialRecord`, which knows its steps.
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
    """One input, resolved to a real directory or file, for staging and provenance."""

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
    """Resolve every input a record declares.

    A supplied path wins; otherwise the input's native location; otherwise,
    when ``strict``, :class:`RecordInputNotSupplied`. An input missing one of
    its declared files is :class:`RecordInputIncomplete`.

    ``strict=False`` is ``describe``'s posture: an input with nothing to
    resolve, or an incomplete one, is left out rather than raising. An unknown
    ``--input`` name is refused either way.
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

    ``command`` is the step's base argv; core does not know what its strings
    mean. An axis may contribute arguments for a step it names
    (``AxisResult.command_arguments``). ``default_arguments`` are passed
    unless an axis passes its own (:class:`DefaultArgument` states the rule);
    the step runs :meth:`argv`: ``command``, the defaults no axis replaced,
    then the axis's contribution.

    ``produces`` and ``consumes`` are tuples of case-relative paths the step
    writes and reads, never artifact ids (those are derived).  ``produces``
    becomes the record's expected artifacts and ``consumes`` the step's DAG
    ``consumes``, which provenance fingerprints. A bare ``str``, ``""``, ``"."``
    and ``{``/``}`` are refused: a ``produces`` path becomes an artifact
    ``path_pattern`` that core ``str.format``-s. A utility manifest's
    ``produces`` is unioned with the step's own. An entry may be a
    :class:`ProducedPath`; a plain path means :data:`PLAIN_FILE_FORMAT`.
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
        """The command line this step runs given an axis's contribution (:class:`DefaultArgument` states the rule)."""
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
                return entry.artifact_format if isinstance(entry, ProducedPath) else PLAIN_FILE_FORMAT
        raise TutorialRecordError(
            f"workflow step {self.step_id!r} does not produce {path!r}; it produces {[str(p) for p in self.produces]}"
        )


@dataclass(frozen=True)
class TutorialRecord:
    """A tutorial as inert data: where its native case lives, what may vary.

    Resolving a record calls no plugin code until an axis it names runs.
    ``native_case_relpath`` is relative to a cases root the caller supplies.

    ``axes`` are the record's own :class:`AxisContract`s; a bare study name
    resolves against these only, so one name may mean different things in two
    records. Two axes sharing a name are refused, and so is a name-to-contract
    mapping.

    ``workflow_variants`` maps a selector value (say, a choice between two
    mesh-generation routes) to the ordered step ids that variant runs; a
    record with one route leaves it empty. ``default_variant`` is the variant
    a study runs when it does not name ``variant_selector``, the route the
    native case runs: required when ``workflow_variants`` is declared, one of
    its keys compared exactly, and refused when there are no variants.
    """

    name: str
    native_case_relpath: str
    workflow_steps: tuple[WorkflowStep, ...]
    #: Data a step reads that is not in the native case folder: each input's
    #: destinations are excluded from the native-case copy at staging time
    #: and overlaid from wherever it resolves to (``resolve_record_inputs``,
    #: ``record_execution._stage``).
    inputs: tuple[RecordInput, ...] = ()
    axes: tuple[AxisContract, ...] = ()
    workflow_variants: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: The reserved study name that selects among ``workflow_variants`` --
    #: declared by the record, never a name core invents (core reserves the
    #: mechanism only, no selector name of its own -- cardiacFOAM's records
    #: declare ``"mesh"`` themselves). ``None`` when the record declares no
    #: variants to select among.
    variant_selector: str | None = None
    #: The ``workflow_variants`` key a study that names no route runs (see
    #: the class docstring). ``None`` exactly when the record declares no
    #: variants.
    default_variant: str | None = None
    #: How ``omnidriver check`` exercises the record briefly against the real
    #: solver; ``None`` for a record that declares none.
    conformance: "ConformanceStudy | None" = None
    #: A record whose solve has nothing to split across processes (one cell):
    #: a run asking for ``parallel`` is refused by name when it is planned.
    serial_only: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise TutorialRecordError("a tutorial record must have a non-empty name")
        if not self.native_case_relpath:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} must declare a native_case_relpath"
            )
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

    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.workflow_steps)

    def axis_names(self) -> tuple[str, ...]:
        return tuple(axis.name for axis in self.axes)

    def _check_inputs(self) -> None:
        """The input refusals that read ``workflow_steps``, which a lone :class:`RecordInput` cannot check."""
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

    Not a ``case_write.ParameterAssignment``: an axis is pure and knows only a
    document, a key path and a value; ``patches_to_parameters`` promotes
    merged patches. It carries no ``validated`` field: the record-key
    validator decides, and ``resolve_case_patches`` puts its answer on
    ``SourcedPatch.validated``.
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
    replaces that default; anything else is appended
    (:class:`DefaultArgument` states the rule).
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


#: An axis's resolution function: the study value and the staged case root,
#: which it may read and must not write (``resolve_case_patches`` checks a
#: digest of the tree).
AxisFunction = Callable[[Any, Path], AxisResult]


@dataclass(frozen=True)
class AxisContract:
    """A named axis: what value it accepts, and the pure function computing its patches and command arguments.

    Core ships no axis; an adapter declares each on the record that uses it.
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
# Selectors: a reserved study name that picks among a record's declared
# `workflow_variants` and produces no patches. Core names none; a record
# declares its own via `TutorialRecord.variant_selector`.
# ---------------------------------------------------------------------------


def resolve_variant_selector(record: TutorialRecord, value: Any) -> tuple[str, ...]:
    """The step ids of the variant ``value`` selects.

    Refused when the record declares no variants, when ``value`` is ``None``,
    or when it does not name a declared variant exactly (no ``str()``
    coercion: ``1`` must not match a variant named ``"1"``).
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


# ---------------------------------------------------------------------------
# Study name sorting
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

    A name containing ``:`` is a ``document:dotted.path`` literal key; the
    document (before the first colon, may contain ``/``) is checked for shape
    only, and the key is left to the stack's record-key validator. A name with
    no colon is an axis name, resolved against ``axes`` and refused when none
    has it.
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
# Combine: conflict refusal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcedPatch:
    """One patch, tagged with its source and the record-key validator's answer for it.

    ``validated`` has no default: every call site states one.
    """

    patch: AxisPatch
    source: str
    validated: bool

    def slot(self) -> str:
        return self.patch.slot()


def _strictly_equal(first: Any, second: Any) -> bool:
    """Same Python type and ``==``, since ``1 == True`` and ``1 == 1.0`` are real conflicts here."""
    return type(first) is type(second) and first == second


def combine_patches(patches: Sequence[SourcedPatch]) -> tuple[SourcedPatch, ...]:
    """Combine every source's patches into one list, refusing a real conflict.

    Two sources naming one (document, key) slot agree when ``value_kind`` and
    the value (strict same-type equality) match, and are otherwise refused
    naming both sources: a later write never silently wins.
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
        # Agreeing patches already went through the same validator in
        # `resolve_case_patches`, so they carry the same `validated`; keep the
        # first.
    return tuple(by_slot.values())


# ---------------------------------------------------------------------------
# Resolving one case's whole study
# ---------------------------------------------------------------------------


def _case_root_digest(case_root: Path) -> str:
    """A digest over every file's path and bytes under ``case_root``."""
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
    """Call the validator, wrapping anything it raises in a ``TutorialRecordError`` that names the document and key."""
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
    workflow_step_ids: Sequence[str] | None = None,
) -> tuple[tuple[SourcedPatch, ...], dict[str, tuple[str, ...]]]:
    """Resolve one case's whole study into a conflict-checked patch list.

    ``study_by_source`` maps a source label (``"base"``, ``"sweep"``) to that
    source's flat ``name -> value`` mapping. Every name is classified, and
    every direct key validated, before any axis runs, so a bad study is
    refused before an axis does any work. Every patch, a direct key's or an
    axis's, goes through ``direct_key_validator``, whose answer becomes
    ``SourcedPatch.validated``.

    ``workflow_step_ids`` are the steps the selected route runs (default: all
    the record's). An axis whose only effect is command arguments for a
    declared step that route does not run is refused, since its value would
    have no effect.

    Returns ``(combined_patches, command_arguments_by_step)``, the latter the
    axes' ``AxisResult.command_arguments`` merged by step id.
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
    route_step_ids = tuple(record.step_ids() if workflow_step_ids is None else workflow_step_ids)
    steps_by_id = {step.step_id: step for step in record.workflow_steps}
    command_arguments: dict[str, tuple[str, ...]] = {}
    command_argument_source: dict[str, str] = {}
    for source, name, sorted_name, value in axis_entries:
        del source  # an axis patch is sourced by the axis's own name, below
        axis = sorted_name.axis
        # `resolve` is adapter code: a value not fitting the axis's declared
        # kind must not reach it and surface as a native coercion error.
        value_kind_reasons = validate_value_shape(axis.value_kind, value)
        if value_kind_reasons:
            raise TutorialRecordError(
                f"axis {name!r} declares value_kind {axis.value_kind!r}, "
                f"but the value {value!r} does not fit it: "
                f"{'; '.join(value_kind_reasons)}"
            )
        # An axis must not write the staged case outside `commit_case_write`.
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
            if step_id not in known_step_ids:
                raise TutorialRecordError(
                    f"axis {name!r} contributes command arguments to step "
                    f"{step_id!r}, which tutorial record {record.name!r} "
                    f"does not declare (declared steps: {sorted(known_step_ids)})"
                )
            if step_id not in route_step_ids and not result.patches:
                raise TutorialRecordError(
                    f"axis {name!r} only contributes command arguments to step {step_id!r}, which "
                    f"the selected route of tutorial record {record.name!r} does not run "
                    f"(it runs {list(route_step_ids)}); drop {name!r} or select a route that "
                    f"runs {step_id!r}"
                )
            extra_args = tuple(extra_args)
            # Refused here rather than when the DAG is built.
            try:
                steps_by_id[step_id].argv(extra_args)
            except TutorialRecordError as exc:
                raise TutorialRecordError(f"axis {name!r}: {exc}") from exc
            existing_args = command_arguments.get(step_id)
            if existing_args is None:
                command_arguments[step_id] = extra_args
                command_argument_source[step_id] = name
                continue
            # Two axes may contribute to one step only when they agree
            # exactly: no concatenation, no later-wins.
            if existing_args != extra_args:
                raise TutorialRecordError(
                    f"step {step_id!r} receives conflicting command arguments "
                    f"from axis {command_argument_source[step_id]!r} "
                    f"({list(existing_args)}) and axis {name!r} ({list(extra_args)})"
                )

    combined = combine_patches(sourced_patches)
    return combined, dict(command_arguments)


# ---------------------------------------------------------------------------
# Unchanged detection
# ---------------------------------------------------------------------------


def split_unchanged(
    patches: Sequence[SourcedPatch],
    *,
    case_root: Path,
    read_current_value: Callable[[Path, str], Any] | None,
    values_agree: Callable[[str, Any, Any], bool] | None,
) -> tuple[tuple[SourcedPatch, ...], tuple[SourcedPatch, ...]]:
    """Split ``patches`` into ``(to_write, unchanged)``.

    Compares with the adapter's typed ``values_agree`` (the stack's
    ``get_case_value_comparator``) against the staged case's current value
    from ``read_current_value`` (its ``get_config_value_reader``), never
    Python equality: a requested ``1e-3`` and a resolved ``0.001`` are one
    value. The reader receives ``patch.key_path`` as a tuple.

    Without a reader or a comparator every patch is reported changed. An
    exception either raises propagates.
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
# Promoting to the real write channel
# ---------------------------------------------------------------------------


def patches_to_parameters(
    patches: Sequence[SourcedPatch],
    *,
    owner: str,
) -> tuple[Any, ...]:
    """Promote a merged, conflict-checked patch list into ``ParameterAssignment`` values for one commit.

    Every assignment has ``source="case"``, a per-case choice. A validated key
    is written whether or not the case holds it (``"ensure"``); an unvalidated
    one only replaces a key the case holds (``"set"``), so a typo cannot add a
    key.
    """
    from .case_write import ParameterAssignment

    return tuple(
        ParameterAssignment(
            qualified_id=sourced.slot(),
            owner=owner,
            document=sourced.patch.document,
            key_path=sourced.patch.key_path,
            value=sourced.patch.value,
            value_kind=sourced.patch.value_kind,
            source="case",
            validated=sourced.validated,
            operation="ensure" if sourced.validated else "set",
        )
        for sourced in patches
    )


# ---------------------------------------------------------------------------
# Building a plugin's own record catalog
# ---------------------------------------------------------------------------


def record_input_destinations(record: "TutorialRecord") -> frozenset[str]:
    """Every case-relative destination any of ``record``'s inputs writes, excluded from the native-case copy at staging."""
    return frozenset(destination for input_ in record.inputs for destination in input_.destinations())


def build_tutorial_record_catalog(
    records: Sequence[TutorialRecord],
    *,
    conformance: Mapping[str, "ConformanceStudy"] | None = None,
) -> dict[str, TutorialRecord]:
    """Build a ``name -> record`` catalog, refusing a duplicate name by name.
    ``conformance`` gives each record it names its :class:`ConformanceStudy`,
    and a name no record has is refused.

    A dict comprehension over a plugin's ``TUTORIAL_RECORDS`` would let a
    second record with the same name silently overwrite the first.
    """
    catalog: dict[str, TutorialRecord] = {}
    studies = dict(conformance or {})
    unknown = sorted(set(studies) - {record.name for record in records})
    if unknown:
        raise TutorialRecordError(f"conformance studies for {unknown}, which are no record of this catalog")
    for record in records:
        if record.name in studies:
            record = dataclasses.replace(record, conformance=studies[record.name])
        if record.name in catalog:
            raise TutorialRecordError(
                f"duplicate tutorial record name {record.name!r}: both "
                f"{catalog[record.name].native_case_relpath!r} and "
                f"{record.native_case_relpath!r} claim it; a record catalog "
                "requires unique names"
            )
        catalog[record.name] = record
    return catalog


def lookup_record(entry: "str | TutorialRecord", *, driver_context: Any) -> TutorialRecord:
    """The record ``entry`` names in the composed stack's catalogue (case
    folded), or ``entry`` itself when it already is one. An unknown name is
    refused with the catalogue's names."""
    if isinstance(entry, TutorialRecord):
        return entry
    catalog = driver_context.stack.call("get_tutorial_records")
    by_name = {name.casefold(): record for name, record in catalog.items()}
    record = by_name.get(entry.strip().casefold())
    if record is None:
        raise TutorialRecordError(
            f"unknown tutorial record {entry!r}; the composed stack registers "
            f"{sorted(catalog) or 'none'}. To run a case folder that is not a "
            "record, pass it with --case"
        )
    return record


def case_folder_record(case_dir: str | Path, *, driver_context: Any) -> tuple[TutorialRecord, Path]:
    """An ad hoc record for a case folder the stack declares an entrypoint for:
    one step running that entrypoint, no axes. Returns the record and the
    cases root (the folder's parent) it is staged from."""
    from .plugin_profile import entrypoint_relpaths

    case = Path(case_dir).expanduser().resolve()
    if not case.is_dir():
        raise TutorialRecordError(f"--case {str(case_dir)!r} is not a directory")
    declared = entrypoint_relpaths(driver_context)
    if not declared:
        raise TutorialRecordError(
            "--case runs a folder's entrypoint, and the composed stack declares none "
            "(case_entrypoints)"
        )
    entrypoint = declared[0]
    if not (case / entrypoint).is_file():
        raise TutorialRecordError(f"--case {str(case)!r} has no {entrypoint!r} to run")
    record = TutorialRecord(
        name=case.name, native_case_relpath=case.name,
        workflow_steps=(WorkflowStep(step_id="run", command=(entrypoint,)),),
    )
    return record, case.parent
