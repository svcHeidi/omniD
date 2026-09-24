"""What a framework-authored case mutation is, before anything is written.

Core owns this vocabulary. A solver adapter fills it with meaning; a format
owner turns it into bytes; core commits those bytes. Nothing in this module
touches a filesystem or knows any dictionary syntax -- it is types and
canonical serialization, and that is what lets it sit in core at all.

Two creation modes, kept distinct because their prerequisites differ:

``clone_and_patch``   an existing case is edited in place or into a clone.
``synthesize``        a case is built from a catalog. Requires explicit source
                      artifacts; a case built from nothing is not a supported
                      mode.

**Corrected 2026-09-23 (Phase 3 Task 1):** this used to declare a third mode,
``generated_input`` ("one input file is authored by an operation"), with an
invented prerequisite -- exactly one distinct document -- so it would differ
from ``clone_and_patch``. Review R2 had already named the two "distinct in
name only"; Phase 2 answered that by inventing a rule instead of finding a
real distinction. Phase 3 Task 1 counted production consumers
(`grep -rn "generated_input" packages/*/src/`): zero. Neither adapter's
`get_supported_mutation_modes` ever named it, no renderer in
`openfoam/case_rendering.py` ever handled it, and the only production
constructors of a `CaseMutationRequest` (`cardiaccore/workflows/overrides.py`,
`cardiacfoam/dict_builder.py`) never built one. It named nothing. Removed,
along with its invented prerequisite.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .contracts.dictionary import VALUE_KINDS, validate_value_shape

#: Bumped whenever a field is added, removed or reinterpreted. A plan
#: serialized under one version is not readable under another: a reader that
#: silently accepts an older payload is a reader that fills a missing field
#: with a default nobody reviewed.
PLAN_SCHEMA_VERSION = 1

PRECONDITION_KINDS = frozenset({
    "file",              # a case file that must have this digest
    "include",           # a file the renderer read through an include directive
    "source_artifact",   # a mesh or template the synthesis consumed
    "environment",       # an environment value the resolution depended on
    "absence",           # a location that must stay empty, because a file
                         # appearing there changes which file is selected
})

#: **Implemented-and-thin, noted 2026-09-23 (Phase 3 Task 1 Step 3).**
#: ``"environment"`` is implemented end to end -- built by
#: ``openfoam/case_rendering.py::patch_preconditions`` and checked by
#: ``case_transaction._check_preconditions`` -- and correct, but it has
#: exactly one emitter today. Do not delete it: Phase 3 Task 5 (``--apply``
#: joining the channel) gives it a second consumer, and it was built for
#: exactly that (see that task's F1b readback). Thin is not the same claim
#: as unused; a later reader should not conflate the two.

MUTATION_MODES = frozenset({"clone_and_patch", "synthesize"})

#: What a `ParameterAssignment` asserts about the document's *final* state,
#: not merely the action that gets it there (2026-09-23 decision, "a
#: parameter asserts a final state, not only a value"). ``set`` is the
#: default and matches every assignment built before this field existed: the
#: key already exists, and must hold this value. ``ensure`` is the same
#: assertion plus "...and if the key is absent, create it" -- the typed
#: counterpart of `mutators.update_foam_entry`'s own `add_if_missing`.
#: ``remove`` asserts the key does not exist; it carries no value at all
#: (enforced in `ParameterAssignment.__post_init__`, the same "digest and
#: must_be_absent are different claims" reasoning `Precondition` already
#: applies). One vocabulary, not three types: a caller that wants to upsert
#: or delete still builds a `ParameterAssignment`, just with a different
#: `operation`.
PARAMETER_OPERATIONS = frozenset({"set", "ensure", "remove"})

#: Where a value came from. These never convert into one another: a tutorial
#: example is not a solver default, and a plausible number is not a validated
#: recommendation. See the plan's "five value sources" table.
VALUE_SOURCES = frozenset({
    "case", "effective", "call_site_default", "template", "recommendation",
})


def _check_case_relative(label: str, value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(f"{label} must be case-relative, not absolute: {value!r}")
    if ".." in path.parts:
        raise ValueError(f"{label} must not escape the case: {value!r}")
    return path


#: The only JSON-representable scalar types. Deliberately excludes ``bytes``:
#: JSON has no byte-string type, and ``RenderedFile.content`` already carries
#: real bytes outside this payload system (see its docstring on why the
#: "referenced by digest" rule does not apply there).
_JSON_SCALAR_TYPES = (type(None), bool, int, float, str)


def _freeze(value: Any) -> Any:
    """Deep-freeze a payload so a "frozen" record has no mutable interior.

    ``@dataclass(frozen=True)`` prevents rebinding a field, not mutating the
    object a field points at. A plan holding a ``dict`` is a reviewed plan whose
    reviewed contents can change after review -- proposal defect W1.

    Also where "a plan payload must be JSON-shaped and immutable" is made
    true rather than merely claimed (R2 finding 3): a mapping key must be a
    ``str`` -- JSON has no other key type, and an int key silently becomes a
    string on a real JSON round trip without changing the plan digest, which
    is how a reviewed plan can drift after review without the stability check
    noticing -- and a non-finite float is refused here too, the same
    ``allow_nan=False`` reasoning ``canonical_json`` applies at digest time,
    but at construction instead of two steps later. Anything that is not a
    mapping, a list/tuple, or one of the JSON scalar types is refused outright
    rather than passed through unchanged, which is what let an arbitrary
    object slip through before while this docstring already promised
    otherwise.
    """
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(
                    f"a plan payload's mapping keys must be strings; JSON has "
                    f"no other key type, so a non-string key silently becomes "
                    f"one on a real round trip. Got key {key!r} of type "
                    f"{type(key).__name__}"
                )
        return MappingProxyType({key: _freeze(item) for key, item in sorted(value.items())})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(
            f"a plan payload must be JSON-representable; got non-finite "
            f"float {value!r}"
        )
    if isinstance(value, _JSON_SCALAR_TYPES):
        return value
    raise TypeError(
        f"a plan payload must be JSON-shaped and immutable; got {type(value).__name__}"
    )


@dataclass(frozen=True)
class ParameterAssignment:
    """One parameter, addressed unambiguously, with its value and its origin."""

    qualified_id: str
    owner: str
    document: str
    key_path: tuple[str, ...]
    binding: Mapping[str, str]
    value: Any
    value_kind: str
    source: str
    allowed_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    unit: str = ""
    evidence_refs: tuple[str, ...] = ()
    operation: str = "set"
    #: Whether the adapter that resolved this key checked it against a real
    #: catalog. Added 2026-09-24 for tutorial-record studies (design doc
    #: ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
    #: §5): a solver-owned key (cardiacFOAM's, checked against
    #: ``dict_entries_catalog``) is ``True``; an environment-owned key with no
    #: full catalog yet (``system/fvSchemes``, ``fvSolution``, ...) is written
    #: anyway, flagged ``False`` -- "no check invented in place of a catalog".
    #: Core never decides this itself; whichever adapter resolves the key
    #: (``core.tutorial_records.resolve_case_patches``'s ``direct_key_validator``,
    #: or an ``AxisContract.resolve`` building an ``AxisPatch``) does. Defaults
    #: ``True``, the same "no field means the prior, only behaviour" reasoning
    #: ``operation``/``evidence_refs``/``expected_effects`` already use --
    #: every assignment built before this field existed came from a channel
    #: that already implied a real catalog check, so schema version stays
    #: unchanged here too, matching that precedent.
    validated: bool = True

    def __post_init__(self) -> None:
        # Coerced to a tuple before anything below reads it (R2 finding 3): a
        # list `key_path` let a caller append to it *after* the duplicate-slot
        # check in `CaseMutationRequest.__post_init__` had already run against
        # the pre-append `slot()`, silently invalidating a check that had
        # already passed.
        object.__setattr__(self, "key_path", tuple(self.key_path))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        _check_case_relative("a parameter's document", self.document)
        if not self.key_path:
            raise ValueError(f"parameter {self.qualified_id!r} names no key")
        if self.source not in VALUE_SOURCES:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares value source "
                f"{self.source!r}; known sources are {sorted(VALUE_SOURCES)}"
            )
        if self.operation not in PARAMETER_OPERATIONS:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares operation "
                f"{self.operation!r}; known operations are "
                f"{sorted(PARAMETER_OPERATIONS)}"
            )
        # 2026-09-23 decision ("a parameter asserts a final state, not only a
        # value"): `remove` asserts absence, which is a different claim from
        # "has this value" -- carrying a value alongside it would be two
        # assertions on one field, so it is refused outright, the same way
        # `Precondition` refuses a `digest` together with `must_be_absent`.
        # `set`/`ensure` still require a value; every declared `VALUE_KINDS`
        # shape check already rejects `None`, but refusing it here first
        # gives a caller a direct answer instead of a shape-mismatch message
        # about `None` not fitting `"scalar"`/`"boolean"`/etc.
        if self.operation == "remove":
            if self.value is not None:
                raise ValueError(
                    f"parameter {self.qualified_id!r} declares operation "
                    f"'remove' but also a value ({self.value!r}); removal "
                    f"asserts the key is absent, which is a different claim "
                    f"from 'has this value' -- Precondition refuses the same "
                    f"combination for `must_be_absent`/`digest`"
                )
        elif self.value is None:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares operation "
                f"{self.operation!r}, which requires a value; only 'remove' "
                f"may omit one"
            )
        # Plan's 2026-09-23 decision ("a parameter value is typed data, never
        # rendered text"): a value is native Python data, checked against its
        # declared shape here, not rendered text checked nowhere. This closes
        # R2 finding 4 -- `value_kind="scalar", value=float("nan")` and
        # `value_kind="banana"` were both accepted before this call existed.
        # `value_kind` itself is always checked, even for `remove` -- it
        # still names the shape of the key being removed, for audit
        # purposes, so `value_kind="banana"` is refused regardless of
        # operation. Only the "does the value fit that shape" half is
        # skipped for `remove`: there is no value to check.
        if self.value_kind not in VALUE_KINDS:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares value_kind "
                f"{self.value_kind!r}, which is not one of "
                f"{sorted(VALUE_KINDS)}"
            )
        if self.operation != "remove":
            shape_reasons = validate_value_shape(self.value_kind, self.value)
            if shape_reasons:
                raise ValueError(
                    f"parameter {self.qualified_id!r} declares value_kind "
                    f"{self.value_kind!r} but its value does not fit: "
                    f"{'; '.join(shape_reasons)}"
                )
        for placeholder, bound in self.binding.items():
            allowed = self.allowed_bindings.get(placeholder)
            if allowed is None:
                raise ValueError(
                    f"parameter {self.qualified_id!r} binds {placeholder!r} but "
                    f"declares no allowed values for it; an undeclared binding "
                    f"writes a key no utility reads"
                )
            if bound not in allowed:
                raise ValueError(
                    f"parameter {self.qualified_id!r} binds {placeholder!r} to "
                    f"{bound!r}, which is not one of {list(allowed)}"
                )
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "binding", _freeze(self.binding))
        object.__setattr__(
            self, "allowed_bindings",
            MappingProxyType({
                key: tuple(values) for key, values in sorted(self.allowed_bindings.items())
            }),
        )

    def slot(self) -> str:
        """The address this assignment occupies, document scope included."""
        return f"{self.document}::{'.'.join(self.expanded_key_path())}"

    def expanded_key_path(self) -> tuple[str, ...]:
        return tuple(self.binding.get(segment, segment) for segment in self.key_path)

    def to_json(self) -> dict[str, Any]:
        return {
            "qualified_id": self.qualified_id,
            "owner": self.owner,
            "document": self.document,
            "key_path": list(self.key_path),
            "binding": dict(self.binding),
            "expanded_key_path": list(self.expanded_key_path()),
            "value": _json_value(self.value),
            "value_kind": self.value_kind,
            "source": self.source,
            "allowed_bindings": {
                key: list(values) for key, values in self.allowed_bindings.items()
            },
            "unit": self.unit,
            "evidence_refs": list(self.evidence_refs),
            "operation": self.operation,
            "validated": self.validated,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ParameterAssignment":
        return cls(
            qualified_id=payload["qualified_id"],
            owner=payload["owner"],
            document=payload["document"],
            key_path=tuple(payload["key_path"]),
            binding=dict(payload["binding"]),
            value=payload["value"],
            value_kind=payload["value_kind"],
            source=payload["source"],
            allowed_bindings={
                key: tuple(values)
                for key, values in payload.get("allowed_bindings", {}).items()
            },
            unit=payload.get("unit", ""),
            # Absent in a plan written before this field existed (schema
            # version unchanged -- see the 2026-09-23 decision's report):
            # every such assignment was implicitly a `set`, so that is the
            # neutral default here, the same "no field means the prior,
            # only behaviour" reasoning `unit`/`evidence_refs` already use.
            operation=payload.get("operation", "set"),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            # Same "no field means the prior, only behaviour" default as
            # `operation` above -- absent in a plan written before this field
            # existed.
            validated=payload.get("validated", True),
        )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class CaseMutationRequest:
    """An explicit request to author case inputs, in a declared mode.

    Each mode's declared prerequisite is enforced, not merely documented (R2
    finding 7): ``clone_and_patch`` assigns at least one parameter or names at
    least one source artifact, and ``synthesize`` names at least one non-empty
    source artifact.

    **Corrected 2026-09-23 (Phase 3 Task 1):** a third prerequisite used to
    live here too -- ``generated_input`` authors exactly one document -- for
    a mode that had no production consumer at all. See the module docstring's
    2026-09-23 note. `clone_and_patch`'s "at least one parameter" rule was
    reconsidered in the same pass and kept as-was: the one production caller
    that could produce a zero-parameter patch
    (`cardiaccore.workflows.overrides.apply_input_overrides_planned`) already
    returns `None` before constructing a request when its overrides resolve
    to nothing, rather than relying on this guard to catch it. At the time,
    "no caller exercises this rule as the thing that stops a real
    zero-parameter patch" was true.

    **Corrected again, 2026-09-23 (Phase 3 Task 7).** A real caller now does:
    `heart_solver_comparison`'s whole-template-file swap assigns zero
    `ParameterAssignment`s (its four documents are copied in verbatim, not
    key/value-patched) but is still a genuine `clone_and_patch` mutation, not
    a no-op. The rule is widened, not dropped: a `clone_and_patch` request
    must still assign at least one parameter OR name at least one source
    artifact -- the same "you must declare what you did" shape `synthesize`
    already has, rather than accepting a request that does neither.

    **Corrected 2026-09-24:** `heart_solver_comparison` was deleted (it
    pointed at a native case that does not exist -- see
    `docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`
    §2/§7). The rule stays widened regardless: `synthesize`'s own "declare
    what you did" shape is the one this mirrors, and a future
    `clone_and_patch` whole-file swap (the same class of mutation, tracked
    for the tutorials still to migrate) would need it again. Weakening a
    validation invariant is not a corollary of deleting the one caller that
    happened to motivate it.

    ``source_artifacts`` are opaque identifiers -- a path, a digest, a URI --
    naming something a mutation consumed (a synthesis, per the original
    design, but now also a `clone_and_patch` whose only content is a declared
    artifact -- see above), and are deliberately NOT case-relative-checked
    the way ``ParameterAssignment.document`` and ``RenderedFile.path`` are: a
    mesh or template a mutation reads from may legitimately live outside the
    case (an externally supplied source), where a document this framework
    writes into never should. Only non-empty, non-whitespace-only is
    enforced here.
    """

    mode: str
    case_root: Path
    adapter_id: str
    workflow: str
    source_artifacts: tuple[str, ...]
    parameters: tuple[ParameterAssignment, ...]
    requested_by: str

    def __post_init__(self) -> None:
        # Coerced before any check reads them (R2 finding 3): a list
        # `parameters`/`source_artifacts` let a caller mutate the stored
        # object in place *after* the duplicate-slot check below had already
        # run against it, silently invalidating a check that had already
        # passed. See the analogous comment on ParameterAssignment.
        object.__setattr__(self, "source_artifacts", tuple(self.source_artifacts))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        # R3 blocker 2 (2026-09-23): a relative `case_root` resolves against
        # whatever directory happens to be current *at commit time*, not at
        # plan time -- two different processes (or the same process after a
        # `chdir`) can commit one plan into two different directories with no
        # error at all. A channel whose entire purpose is auditability must
        # refuse that at construction, before a plan built on this request
        # can even exist, not discover it later inside `commit_case_write`.
        if not Path(self.case_root).is_absolute():
            raise ValueError(
                f"case_root must be absolute, not {str(self.case_root)!r}; a "
                f"relative root resolves against whatever directory the "
                f"process committing the plan happens to be in, so the same "
                f"plan could silently write into two different places -- "
                f"which is not auditable"
            )
        if self.mode not in MUTATION_MODES:
            raise ValueError(
                f"unsupported creation mode {self.mode!r}; supported modes are "
                f"{sorted(MUTATION_MODES)}"
            )
        for artifact in self.source_artifacts:
            if not isinstance(artifact, str) or not artifact.strip():
                raise ValueError(
                    f"a source artifact must be a non-empty, non-whitespace "
                    f"identifier; got {artifact!r}. An empty string declares "
                    f"a source naming nothing"
                )
        if self.mode == "synthesize" and not self.source_artifacts:
            raise ValueError(
                "a synthesize request must name at least one source artifact; a "
                "case built from no declared source is not a supported creation "
                "mode"
            )
        # **Corrected 2026-09-23 (Phase 3 Task 7).** This used to require at
        # least one `ParameterAssignment` outright. Task 1 kept that rule
        # after finding "no caller needs this rule relaxed" -- true at the
        # time, false then: `heart_solver_comparison`'s whole-template-file
        # swap was a real `clone_and_patch` mutation with zero key/value
        # assignments. Widened to mirror `synthesize`'s own "you must declare
        # what you did" invariant: a clone_and_patch request now satisfies it
        # with a parameter OR a named source artifact -- not neither. A
        # request with both empty still patches nothing and is still refused.
        #
        # **Corrected 2026-09-24:** `heart_solver_comparison` was deleted --
        # it pointed at no native case. `manufactured_purkinje_graph`'s own
        # `purkinjeGraph.<id>` copy, once floated here as a second example,
        # stays a direct write outside this channel entirely (no artifact
        # staging primitive yet -- see that tutorial's own `_apply_case`
        # docstring), so it does not actually exercise this branch. The rule
        # stays widened anyway: it mirrors `synthesize`'s own invariant, and
        # a future `clone_and_patch` whole-file swap would need it again.
        if self.mode == "clone_and_patch" and not self.parameters and not self.source_artifacts:
            raise ValueError(
                "a clone_and_patch request must assign at least one "
                "parameter or name at least one source artifact; a patch "
                "that neither assigns nor declares anything is not a "
                "supported creation mode"
            )
        seen: dict[str, str] = {}
        for parameter in self.parameters:
            slot = parameter.slot()
            if slot in seen:
                raise ValueError(
                    f"slot {slot!r} is assigned twice, by {seen[slot]!r} and "
                    f"{parameter.qualified_id!r}; which one survives would "
                    f"depend on iteration order"
                )
            seen[slot] = parameter.qualified_id

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "case_root": str(self.case_root),
            "adapter_id": self.adapter_id,
            "workflow": self.workflow,
            "source_artifacts": list(self.source_artifacts),
            "parameters": [parameter.to_json() for parameter in self.parameters],
            "requested_by": self.requested_by,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CaseMutationRequest":
        return cls(
            mode=payload["mode"],
            case_root=Path(payload["case_root"]),
            adapter_id=payload["adapter_id"],
            workflow=payload["workflow"],
            source_artifacts=tuple(payload["source_artifacts"]),
            parameters=tuple(
                ParameterAssignment.from_json(item) for item in payload["parameters"]
            ),
            requested_by=payload["requested_by"],
        )


def canonical_json(payload: Any) -> str:
    """The one serialization a digest is taken over.

    ``sort_keys`` and fixed separators, so dict iteration order cannot enter a
    digest. ``allow_nan=False``, because ``NaN`` is not JSON and a payload
    carrying one round-trips into something a reader cannot parse.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False,
    )


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class RenderedFile:
    """One file's complete proposed content, as its format owner rendered it.

    ``content`` is embedded in the plan whole, base64-encoded, not merely
    digested. The global "large assets are referenced by digest, never
    embedded" rule is about meshes and VTU output -- this channel's actual
    subject, a rendered dictionary or input file, is typically kilobytes, and
    a reviewer (or a later recovery reader, Task 6) needs the real bytes, not
    a hash of bytes it does not have. ``content_digest`` stays as a derived,
    quick-to-compare integrity check over exactly those bytes.
    """

    path: str
    content: bytes
    mode: int | None
    exists_before: bool
    before_digest: str | None
    renderer_id: str
    format: str

    def __post_init__(self) -> None:
        _check_case_relative("a rendered file's path", self.path)
        if not isinstance(self.content, bytes):
            raise TypeError(
                f"rendered content for {self.path!r} must be bytes, not "
                f"{type(self.content).__name__}; core does not encode text it "
                f"cannot read"
            )
        if self.exists_before and not self.before_digest:
            raise ValueError(
                f"{self.path!r} is declared to exist before the write but "
                f"carries no before-digest; a conflict check needs one"
            )
        if not self.exists_before and self.before_digest:
            raise ValueError(
                f"{self.path!r} is declared absent before the write but carries "
                f"a before-digest"
            )

    @property
    def content_digest(self) -> str:
        return _digest_bytes(self.content)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_digest": self.content_digest,
            "content_bytes": len(self.content),
            "content_base64": base64.b64encode(self.content).decode("ascii"),
            "mode": self.mode,
            "exists_before": self.exists_before,
            "before_digest": self.before_digest,
            "renderer_id": self.renderer_id,
            "format": self.format,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RenderedFile":
        # R2 finding 12: this used to recompute content_digest from the
        # decoded bytes and never compare it against the stored one, so a
        # tampered or corrupted content_digest was silently discarded rather
        # than caught -- the opposite of what "an integrity check" promises.
        content = base64.b64decode(payload["content_base64"])
        stored_digest = payload["content_digest"]
        computed_digest = _digest_bytes(content)
        if stored_digest != computed_digest:
            raise ValueError(
                f"{payload['path']!r} content_digest {stored_digest!r} does "
                f"not match the decoded bytes (which hash to "
                f"{computed_digest!r}); the payload was tampered with or "
                f"corrupted"
            )
        return cls(
            path=payload["path"],
            content=content,
            mode=payload["mode"],
            exists_before=payload["exists_before"],
            before_digest=payload["before_digest"],
            renderer_id=payload["renderer_id"],
            format=payload["format"],
        )


@dataclass(frozen=True)
class Precondition:
    """One fact that must still hold when the plan is committed."""

    kind: str
    target: str
    digest: str | None
    must_be_absent: bool

    def __post_init__(self) -> None:
        if self.kind not in PRECONDITION_KINDS:
            raise ValueError(
                f"a precondition may not guess its kind: {self.kind!r} is not "
                f"one of {sorted(PRECONDITION_KINDS)}"
            )
        if self.must_be_absent and self.digest:
            raise ValueError(
                f"precondition on {self.target!r} requires the target to be "
                f"absent and also to have a digest; those are different claims"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "target": self.target,
            "digest": self.digest, "must_be_absent": self.must_be_absent,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "Precondition":
        return cls(
            kind=payload["kind"], target=payload["target"],
            digest=payload["digest"], must_be_absent=payload["must_be_absent"],
        )


@dataclass(frozen=True)
class CaseWritePlan:
    """Everything that will happen, reviewable before any of it does.

    The plan holds no execution state. Before-*images* live in the journal
    (:mod:`omnidriver.core.case_transaction`); before-*digests* live here,
    because a conflict check is part of what a reviewer approves.

    ``expected_effects`` (added 2026-09-24, Phase 3 Task 9, "the `describe`
    seam"): threaded straight from the ``ResolvedMutation`` every producer
    already builds before constructing this plan. Task 1 (2026-09-23) found
    this same data computed by both producers and read by nothing --
    ``CaseWritePlan`` had no field for it, so it was discarded on every real
    call. This gives it its first consumer: ``commit_case_write`` copies it
    onto the returned ``CaseWriteRecord``, which is how ``describe`` (Task 9)
    reads what a real ``plan_case`` invocation, run against a disposable
    staged clone, actually proposes to change -- without core inventing a
    second, hand-maintained description of the same facts.
    """

    request: CaseMutationRequest
    files: tuple[RenderedFile, ...]
    preconditions: tuple[Precondition, ...]
    semantic_owner_id: str
    stack_identity: str
    created_at: str
    schema_version: int = PLAN_SCHEMA_VERSION
    expected_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Coerced before the duplicate-path check below reads them (R2
        # finding 3): a list `files` let a caller `.append()` a colliding
        # path onto the SAME object this check had already approved,
        # silently changing `plan_digest` after review. See the analogous
        # comment on ParameterAssignment.
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))
        # R2 finding 12: schema_version was checked only in from_json, so a
        # plan constructed directly (not read back from a persisted payload)
        # with schema_version=99 was accepted outright. And a plan with zero
        # files -- nothing to write, so committing it would be a no-op
        # dressed as a mutation -- was also accepted.
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"plan schema version {self.schema_version!r} is not "
                f"{PLAN_SCHEMA_VERSION}"
            )
        if not self.files:
            raise ValueError(
                "a plan must render at least one file; a plan with nothing "
                "to write commits nothing"
            )
        seen: set[str] = set()
        for rendered in self.files:
            if rendered.path in seen:
                raise ValueError(
                    f"{rendered.path!r} is written twice by one plan; the "
                    f"surviving content would depend on ordering"
                )
            seen.add(rendered.path)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.to_json(),
            "files": [rendered.to_json() for rendered in self.files],
            "preconditions": [p.to_json() for p in self.preconditions],
            "semantic_owner_id": self.semantic_owner_id,
            "stack_identity": self.stack_identity,
            "created_at": self.created_at,
            "expected_effects": list(self.expected_effects),
        }

    @property
    def plan_digest(self) -> str:
        return hashlib.sha256(canonical_json(self._digest_payload()).encode()).hexdigest()

    def _digest_payload(self) -> dict[str, Any]:
        """``to_json()`` with order-irrelevant lists canonically sorted.

        R2 finding 12: ``files`` and ``request.parameters`` cannot contain
        two entries at the same path/slot (enforced above and in
        ``CaseMutationRequest.__post_init__``), so their as-written order is
        not semantically meaningful -- but ``plan_digest`` hashed them
        as-given, so two plans differing only in list order digested
        differently. That breaks Task 6's replay/staleness comparison with a
        spurious mismatch. Sorted here, not in ``to_json()``, so a reviewer
        still sees the plan in the order it was authored; only the digest is
        canonicalized.
        """
        payload = self.to_json()
        payload["files"] = sorted(payload["files"], key=lambda f: f["path"])
        payload["request"]["parameters"] = sorted(
            payload["request"]["parameters"],
            key=lambda p: f"{p['document']}::{'.'.join(p['expanded_key_path'])}",
        )
        # Same reasoning as the two sorts above, extended 2026-09-24 (Task 9):
        # `expected_effects` is positionally aligned with `targets`/
        # `parameters` at construction time, not a keyed structure -- two
        # plans differing only in that construction order would otherwise
        # digest differently for no semantic reason.
        payload["expected_effects"] = sorted(payload["expected_effects"])
        return payload

    @property
    def plan_id(self) -> str:
        return self.plan_digest[:16]

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CaseWritePlan":
        version = payload.get("schema_version")
        if version != PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"plan schema version {version!r} is not {PLAN_SCHEMA_VERSION}; "
                f"reading it would mean filling fields nobody reviewed"
            )
        return cls(
            request=CaseMutationRequest.from_json(payload["request"]),
            files=tuple(RenderedFile.from_json(item) for item in payload["files"]),
            preconditions=tuple(
                Precondition.from_json(item) for item in payload["preconditions"]
            ),
            semantic_owner_id=payload["semantic_owner_id"],
            stack_identity=payload["stack_identity"],
            created_at=payload["created_at"],
            schema_version=version,
            # Absent in a plan payload written before this field existed
            # (schema_version unchanged -- the same "no field means the
            # prior, only behaviour" reasoning `ParameterAssignment.from_json`
            # already uses for `operation`): an empty tuple is the neutral,
            # honest default, not a guess at what an old plan expected.
            expected_effects=tuple(payload.get("expected_effects", ())),
        )


@dataclass(frozen=True)
class CaseWriteRecord:
    """What a committed transaction actually did. Not part of the plan.

    ``parameters`` and ``expected_effects`` (added 2026-09-24, Phase 3
    Task 9): copied from the committed ``CaseWritePlan`` by
    ``commit_case_write`` -- ``parameters`` is
    ``[p.to_json() for p in plan.request.parameters]`` (the same validated
    ``ParameterAssignment``s the channel wrote from, not a second
    description of them), ``expected_effects`` is ``plan.expected_effects``
    unchanged. This is ``expected_effects``'s first real consumer: Task 1
    found it computed by every producer and read by nothing.  ``describe``
    reads both off a real ``plan_case`` invocation run against a disposable
    staged case clone (see ``core.introspection``) to answer "what will this
    change" without core inventing a parallel, adapter-specific mapping.
    """

    transaction_id: str
    plan_id: str
    plan_digest: str
    committed: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]
    status: str
    parameters: tuple[Mapping[str, Any], ...] = ()
    expected_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # R2 finding 3: `rec.committed[0]["a"] = 999` worked, because these
        # were plain dicts inside a tuple whose OWN outer immutability said
        # nothing about its elements. Deep-freeze each entry the same way
        # `ResolvedMutation.targets` now is.
        object.__setattr__(self, "committed", tuple(_freeze(entry) for entry in self.committed))
        object.__setattr__(self, "evidence", tuple(_freeze(entry) for entry in self.evidence))
        object.__setattr__(self, "parameters", tuple(_freeze(entry) for entry in self.parameters))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))

    def to_json(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "committed": [dict(entry) for entry in self.committed],
            "evidence": [dict(entry) for entry in self.evidence],
            "status": self.status,
            # `dict(entry)` (the shallow unfreeze `committed`/`evidence` use
            # below) only un-wraps the outermost `MappingProxyType`; a
            # parameter's own nested `binding`/`allowed_bindings` mappings
            # would still be frozen underneath it and fail JSON
            # serialization. `_json_value` already recurses through every
            # `Mapping` (a `MappingProxyType` included) and `tuple`, which is
            # exactly what `_freeze`'s deep-freeze needs undone by.
            "parameters": [_json_value(entry) for entry in self.parameters],
            "expected_effects": list(self.expected_effects),
        }


@dataclass(frozen=True)
class ResolvedMutation:
    """The semantic owner's answer: concrete addresses and expected effects.

    Pure. Produced without reading the case, so a dry run costs nothing and
    changes nothing. The renderer reads; this does not.

    **Audited 2026-09-23 (Phase 3 Task 1 Step 3).** Not a pure passthrough
    container: it earns its type. ``targets`` is genuinely consumed, not
    forwarded whole -- ``case_rendering._document_edits`` groups it by
    document and ``formats()`` derives a value from it that neither producer
    hands over directly. ``__post_init__`` also enforces a real invariant
    (deep-freezing ``targets`` the same way every other declared-tuple field
    in this module is, per R2 finding 3) that a plain container would not.

    ``preconditions`` and ``semantic_owner_id``, by contrast, *are* passed
    straight through untouched by both producers
    (``cardiaccore/workflows/overrides.py::resolve_patch_mutation``,
    ``cardiacfoam/dict_builder.py``'s synthesis resolver) into
    ``CaseWritePlan`` unchanged -- that is expected of a resolve/render
    boundary and not itself a defect.

    ``expected_effects`` is a different finding: both producers build one
    (human-readable strings describing what will change), but
    ``CaseWritePlan`` has no ``expected_effects`` field, and nothing else
    reads this one either (checked: no reference outside its own producers,
    this class, and tests that merely supply ``()``). It is computed and then
    discarded on every real call. Recommendation: either give it a consumer
    (an evidence/record field, or a `describe`-style preview) or drop it in
    a later task once nothing writes it either -- but that is Tasks 2-6's
    call, not this one's: removing a field mid-plan while those tasks still
    build on this type is worse than carrying one thin field.
    """

    request: CaseMutationRequest
    targets: tuple[Mapping[str, Any], ...]
    preconditions: tuple[Precondition, ...]
    expected_effects: tuple[str, ...]
    semantic_owner_id: str

    def __post_init__(self) -> None:
        # Coerced and deep-frozen, the same as every other declared-tuple
        # field in this module (R2 finding 3): `targets` holds plain mappings
        # -- unlike `RenderedFile`/`Precondition`, which are themselves frozen
        # dataclasses -- so it needs `_freeze`, not just a tuple() call.
        object.__setattr__(self, "targets", tuple(_freeze(target) for target in self.targets))
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted({str(target["format"]) for target in self.targets}))
