"""A tutorial record: data, not a factory -- and the axis contract it draws on.

Design: ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
§3 ("Components and ownership"), §4 ("One case, step by step"), §5
("Refusals, the OpenFOAM-key exception, and enforcement").

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

Zero cardiac or OpenFOAM vocabulary lives here, and none may be added --
``scripts/check-import-boundaries.py`` and the core vocabulary tests guard
that the same way they guard every other core module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .case_write import _check_case_relative


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
    does not know what any of these strings mean -- ``cardiacFoam``,
    ``blockMesh -dict ...`` are the adapter's own vocabulary.
    """

    step_id: str
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        if not self.step_id:
            raise TutorialRecordError("a workflow step must have a non-empty step_id")


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
    ``workflow_variants`` maps a selector value (e.g. cardiacFoam's
    ``hex``/``tet`` mesh choice) to the ordered tuple of step ids that
    variant runs; a record with one meshing route leaves this empty.
    """

    name: str
    native_case_relpath: str
    allowed_axes: frozenset[str]
    workflow_steps: tuple[WorkflowStep, ...]
    workflow_variants: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise TutorialRecordError("a tutorial record must have a non-empty name")
        if not self.native_case_relpath:
            raise TutorialRecordError(
                f"tutorial record {self.name!r} must declare a native_case_relpath"
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
    only a document, a key path, a value, and how validated the resolving
    adapter considers it. ``patches_to_parameters`` promotes a merged,
    conflict-checked set of these into real ``ParameterAssignment``s.

    ``validated`` mirrors ``case_write.ParameterAssignment.validated``
    exactly (design §5's OpenFOAM-owned-key exception): ``True`` for a key
    checked against a real catalog, ``False`` for one written because the
    study asked, with no catalog to check it against.
    """

    document: str
    key_path: tuple[str, ...]
    value: Any
    value_kind: str
    validated: bool = True

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
#: ``blockMeshDict``'s extents, and must not write it; nothing here enforces
#: that mechanically, see the design's §5 static-gate note).
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
    contain ``/``, e.g. ``constant/electroProperties``), the rest is a
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
    """One patch, tagged with where it came from -- for conflict messages."""

    patch: AxisPatch
    source: str

    def slot(self) -> str:
        return self.patch.slot()


def combine_patches(patches: Sequence[SourcedPatch]) -> tuple[SourcedPatch, ...]:
    """Step 6, 'Combine' (design §4): one list, refusing a real conflict.

    Two sources naming the same (document, key) slot are fine when they
    agree on the value -- e.g. a study restates a base default explicitly --
    and refused, BY NAME, naming both sources, when they do not. This is the
    tutorial-record replacement for ``cardiacfoam.overrides.merge_assignments``'s
    "later write wins": that behaviour is left exactly as it is for old
    factory tutorials (design §4 step 6's own instruction), which never call
    this function.
    """
    by_slot: dict[str, SourcedPatch] = {}
    for sourced in patches:
        slot = sourced.slot()
        existing = by_slot.get(slot)
        if existing is None:
            by_slot[slot] = sourced
            continue
        if existing.patch.value != sourced.patch.value:
            raise TutorialRecordError(
                f"{slot!r} is set to different values by {existing.source!r} "
                f"({existing.patch.value!r}) and {sourced.source!r} "
                f"({sourced.patch.value!r})"
            )
        # Same value from two sources: prefer whichever is validated, if
        # exactly one of the two is -- an adapter-validated agreement is
        # strictly more informative than an unvalidated one that happens to
        # match it.
        if sourced.patch.validated and not existing.patch.validated:
            by_slot[slot] = sourced
    return tuple(by_slot.values())


# ---------------------------------------------------------------------------
# Resolving one case's whole study (design §4 steps 4-6)
# ---------------------------------------------------------------------------


DirectKeyValidator = Callable[[str, tuple[str, ...], Any], tuple[str, bool]]


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

    sourced_patches: list[SourcedPatch] = []
    command_arguments: dict[str, list[str]] = {}
    for source, name, sorted_name, value in classified:
        if isinstance(sorted_name, DocumentKeyName):
            value_kind, validated = direct_key_validator(
                sorted_name.document, sorted_name.key_path, value,
            )
            patch = AxisPatch(
                document=sorted_name.document, key_path=sorted_name.key_path,
                value=value, value_kind=value_kind, validated=validated,
            )
            sourced_patches.append(SourcedPatch(patch=patch, source=source))
            continue

        axis = sorted_name.axis
        result = axis.resolve(value, staged_case_root)
        for patch in result.patches:
            sourced_patches.append(SourcedPatch(patch=patch, source=name))
        for step_id, extra_args in result.command_arguments.items():
            command_arguments.setdefault(step_id, []).extend(extra_args)

    combined = combine_patches(sourced_patches)
    return combined, {step: tuple(args) for step, args in command_arguments.items()}


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
    docstring for why). A patch this function cannot evaluate -- no reader,
    no comparator, an unreadable current value, or a comparator that itself
    reports it cannot tell -- is treated as CHANGED, never silently dropped:
    an "unchanged" claim this function cannot back is not made.
    """
    if read_current_value is None or values_agree is None:
        return tuple(patches), ()
    to_write: list[SourcedPatch] = []
    unchanged: list[SourcedPatch] = []
    for sourced in patches:
        patch = sourced.patch
        document_path = Path(case_root) / patch.document
        current = read_current_value(document_path, ".".join(patch.key_path))
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
    reasoning ``cardiacfoam.overrides.resolve_entry_overrides`` documents for
    its own ``source="case"`` assignments.
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
            validated=sourced.patch.validated,
        )
        for sourced in patches
    )
