"""What a framework-authored case mutation is, before anything is written.

Core owns this vocabulary. A solver adapter fills it with meaning; a format
owner turns it into bytes; core commits those bytes. Nothing in this module
touches a filesystem or knows any dictionary syntax -- it is types and
canonical serialization, and that is what lets it sit in core at all.

Three creation modes, kept distinct because their prerequisites differ:

``clone_and_patch``   an existing case is edited in place or into a clone.
``synthesize``        a case is built from a catalog. Requires explicit source
                      artifacts; a case built from nothing is not a supported
                      mode.
``generated_input``   one input file is authored by an operation.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

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

MUTATION_MODES = frozenset({"clone_and_patch", "synthesize", "generated_input"})

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


def _freeze(value: Any) -> Any:
    """Deep-freeze a payload so a "frozen" record has no mutable interior.

    ``@dataclass(frozen=True)`` prevents rebinding a field, not mutating the
    object a field points at. A plan holding a ``dict`` is a reviewed plan whose
    reviewed contents can change after review -- proposal defect W1.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in sorted(value.items())})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (bytearray, set)):
        raise TypeError(
            f"a plan payload must be JSON-shaped and immutable; got {type(value).__name__}"
        )
    return value


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

    def __post_init__(self) -> None:
        _check_case_relative("a parameter's document", self.document)
        if not self.key_path:
            raise ValueError(f"parameter {self.qualified_id!r} names no key")
        if self.source not in VALUE_SOURCES:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares value source "
                f"{self.source!r}; known sources are {sorted(VALUE_SOURCES)}"
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
            evidence_refs=tuple(payload.get("evidence_refs", ())),
        )


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class CaseMutationRequest:
    """An explicit request to author case inputs, in a declared mode."""

    mode: str
    case_root: Path
    adapter_id: str
    workflow: str
    source_artifacts: tuple[str, ...]
    parameters: tuple[ParameterAssignment, ...]
    requested_by: str

    def __post_init__(self) -> None:
        if self.mode not in MUTATION_MODES:
            raise ValueError(
                f"unsupported creation mode {self.mode!r}; supported modes are "
                f"{sorted(MUTATION_MODES)}"
            )
        if self.mode == "synthesize" and not self.source_artifacts:
            raise ValueError(
                "a synthesize request must name at least one source artifact; a "
                "case built from no declared source is not a supported creation "
                "mode"
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
        return cls(
            path=payload["path"],
            content=base64.b64decode(payload["content_base64"]),
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
    """

    request: CaseMutationRequest
    files: tuple[RenderedFile, ...]
    preconditions: tuple[Precondition, ...]
    semantic_owner_id: str
    stack_identity: str
    created_at: str
    schema_version: int = PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
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
        }

    @property
    def plan_digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_json()).encode()).hexdigest()

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
        )


@dataclass(frozen=True)
class CaseWriteRecord:
    """What a committed transaction actually did. Not part of the plan."""

    transaction_id: str
    plan_id: str
    plan_digest: str
    committed: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]
    status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "committed": [dict(entry) for entry in self.committed],
            "evidence": [dict(entry) for entry in self.evidence],
            "status": self.status,
        }


@dataclass(frozen=True)
class ResolvedMutation:
    """The semantic owner's answer: concrete addresses and expected effects.

    Pure. Produced without reading the case, so a dry run costs nothing and
    changes nothing. The renderer reads; this does not.
    """

    request: CaseMutationRequest
    targets: tuple[Mapping[str, Any], ...]
    preconditions: tuple[Precondition, ...]
    expected_effects: tuple[str, ...]
    semantic_owner_id: str

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted({str(target["format"]) for target in self.targets}))
