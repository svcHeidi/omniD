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
from pathlib import Path
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


@dataclass(frozen=True)
class WorkflowStep:
    """One named step in a tutorial record's workflow.

    ``command`` is the step's base argv; an axis may contribute additional
    arguments for a step it names (``AxisResult.command_arguments``),
    appended in axis-declaration order (see ``resolve_case_patches``). Core
    does not know what any of these strings mean -- the solver binary's own
    name, or a mesh-generation tool's flags, are the adapter's own
    vocabulary.

    ``produces`` and ``consumes`` are case-relative paths the step writes
    and reads (K4, docs/superpowers/specs/2026-09-25-solver-conformance-
    and-opencarp-design.md §5). ``produces`` becomes the record's expected
    artifacts; ``consumes`` becomes the step's DAG ``consumes``, which
    provenance fingerprints. Paths here, never artifact ids: the ids are
    derived (``record_execution.record_artifact_id``).

    Each is a tuple of non-empty, case-relative ``str`` paths (fix round 1
    M1, 2026-09-25): a bare ``str`` is refused rather than exploded into
    one-character paths; ``""`` and ``"."`` (the case root itself) are
    refused; so are ``{`` and ``}``, because a ``produces`` path becomes an
    artifact ``path_pattern`` that core ``str.format``-s -- the
    ``{case_id}``/``{time}`` placeholders are not supported here.
    """

    step_id: str
    command: tuple[str, ...]
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
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

    ``allowed_axes`` is a closed set: a bare study name not in this set is
    refused (design §5, "an axis the record does not allow"), even when the
    composed stack happens to provide an axis by that name.

    ``workflow_steps`` are keyed by ``step_id``, for ``workflow_variants``
    and for axes that contribute command arguments to a named step.
    ``workflow_variants`` maps a selector value (e.g. an adapter's choice
    between two mesh-generation routes) to the ordered tuple of step ids
    that variant runs; a record with one route leaves this empty.
    """

    name: str
    native_case_relpath: str
    allowed_axes: frozenset[str]
    workflow_steps: tuple[WorkflowStep, ...]
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
        object.__setattr__(self, "allowed_axes", frozenset(self.allowed_axes))
        object.__setattr__(self, "workflow_steps", tuple(self.workflow_steps))
        step_ids = [step.step_id for step in self.workflow_steps]
        if len(set(step_ids)) != len(step_ids):
            raise TutorialRecordError(
                f"tutorial record {self.name!r} declares duplicate workflow "
                f"step ids: {step_ids}"
            )
        known_steps = frozenset(step_ids)
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

    def step_ids(self) -> tuple[str, ...]:
        return tuple(step.step_id for step in self.workflow_steps)


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
    provides axes through ``AxisCapability``, following the same
    provider-stack pattern every other capability uses.
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
    allowed_axes: frozenset[str],
    axis_catalog: Mapping[str, AxisContract],
) -> DocumentKeyName | AxisMatch:
    """Classify one study name, refusing by name before anything runs.

    A name containing ``:`` is a ``document:dotted.path`` literal key (design
    §3): the document is the substring before the FIRST colon (itself may
    contain ``/``, e.g. ``constant/someProperties``), the rest is a
    dot-joined key path. Its document is checked for shape only (case-
    relative, no ``..`` escape, non-empty) -- whether the key itself is one a
    real catalog recognises is adapter work, resolved later by
    ``RecordKeyValidationCapability`` (``resolve_case_patches``), not here.

    A name with no colon is a bare axis name: refused unless it is BOTH
    declared allowed by the record (``allowed_axes``) AND actually provided
    by the composed stack (``axis_catalog``) -- an axis a record allows but
    no adapter provides, or one an adapter provides but this record does not
    allow, are both refusals, and each names the specific reason.
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

    if name not in allowed_axes:
        if name in axis_catalog:
            raise TutorialRecordError(
                f"{name!r} is an axis this entry does not allow (allowed "
                f"axes: {sorted(allowed_axes)})"
            )
        raise TutorialRecordError(
            f"{name!r} is neither a 'document:dotted.path' key nor an axis "
            f"this entry allows (allowed axes: {sorted(allowed_axes)})"
        )
    axis = axis_catalog.get(name)
    if axis is None:
        raise TutorialRecordError(
            f"{name!r} is an allowed axis, but no composed adapter provides "
            f"an axis by that name (provided axes: {sorted(axis_catalog)})"
        )
    return AxisMatch(axis=axis)


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
    axis_catalog: Mapping[str, AxisContract],
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
            sorted_name = sort_study_name(
                name, allowed_axes=record.allowed_axes, axis_catalog=axis_catalog,
            )
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
