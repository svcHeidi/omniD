"""What a framework-authored case mutation is, before anything is written: types, canonical serialization,
and the two calls (:func:`resolve_mutation`, :func:`render_mutation`) that ask the stack to resolve and render.
Core knows no dictionary syntax; a format owner turns a mutation into bytes and core commits them."""

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

class CaseKeyNotFound(KeyError):
    """A writer was asked to edit a key or block its document does not hold. The one ``KeyError`` a
    tutorial record's case write turns into a refusal by name; any other is a defect and propagates."""


#: Bumped whenever a field is added, removed or reinterpreted. A plan
#: serialized under one version is not readable under another: a reader that
#: accepted an older payload would fill a missing field with a default nobody
#: reviewed.
PLAN_SCHEMA_VERSION = 2

#: ``clone_and_patch`` edits an existing case in place or into a clone;
#: ``synthesize`` builds a case from a catalog and requires explicit source
#: artifacts.
MUTATION_MODES = frozenset({"clone_and_patch", "synthesize"})

#: What a `ParameterAssignment` asserts about the document's *final* state.
#: ``set``: the key exists and holds this value. ``ensure``: the same, creating
#: the key when absent. ``remove``: the key does not exist, and no value is
#: carried.
PARAMETER_OPERATIONS = frozenset({"set", "ensure", "remove"})

#: Where a value came from. These never convert into one another: a tutorial
#: example is not a solver default, and a plausible number is not a validated
#: recommendation.
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


#: The only JSON-representable scalar types. Excludes ``bytes``, which JSON
#: cannot carry; ``RenderedFile.content`` holds real bytes outside this system.
_JSON_SCALAR_TYPES = (type(None), bool, int, float, str)


def _freeze(value: Any) -> Any:
    """Deep-freeze a JSON-shaped payload; refuse a non-string key (it would change on a JSON round trip), a non-finite float or any other type."""
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
    value: Any
    value_kind: str
    source: str
    operation: str = "set"
    #: Whether the adapter that resolved this key checked it against a real
    #: catalog; core never decides this itself (``resolve_case_patches``'s
    #: ``direct_key_validator`` and the stack's ``get_record_key_validator``
    #: do). Tri-state: ``None`` means no opinion was formed, which is not the
    #: same as one that passed.
    validated: bool | None = None

    def __post_init__(self) -> None:
        # A list key_path could be appended to after the duplicate-slot check
        # in `CaseMutationRequest` ran against the earlier `slot()`.
        object.__setattr__(self, "key_path", tuple(self.key_path))
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
        # Tri-state, not truthy: the string "false" must be refused.
        if self.validated is not None and not isinstance(self.validated, bool):
            raise TypeError(
                f"parameter {self.qualified_id!r} declares validated="
                f"{self.validated!r}; must be a bool or None (not stated), "
                f"got {type(self.validated).__name__}"
            )
        # `remove` asserts absence, so a value beside it would be two claims
        # on one field; refusing a missing value for `set`/`ensure` here gives
        # a direct answer rather than a shape mismatch about `None`.
        if self.operation == "remove":
            if self.value is not None:
                raise ValueError(
                    f"parameter {self.qualified_id!r} declares operation "
                    f"'remove' but also a value ({self.value!r}); removal "
                    f"asserts the key is absent, which is a different claim "
                    f"from 'has this value'"
                )
        elif self.value is None:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares operation "
                f"{self.operation!r}, which requires a value; only 'remove' "
                f"may omit one"
            )
        # `value_kind` is checked even for `remove` (it names the removed
        # key's shape for audit); only the value-fits-shape check is skipped.
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
        object.__setattr__(self, "value", _freeze(self.value))

    def slot(self) -> str:
        """The address this assignment occupies, document scope included."""
        return f"{self.document}::{'.'.join(self.expanded_key_path())}"

    def expanded_key_path(self) -> tuple[str, ...]:
        return self.key_path

    def to_json(self) -> dict[str, Any]:
        return {
            "qualified_id": self.qualified_id,
            "owner": self.owner,
            "document": self.document,
            "key_path": list(self.key_path),
            "expanded_key_path": list(self.expanded_key_path()),
            "value": _json_value(self.value),
            "value_kind": self.value_kind,
            "source": self.source,
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
            value=payload["value"],
            value_kind=payload["value_kind"],
            source=payload["source"],
            operation=payload["operation"],
            validated=payload["validated"],
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

    ``clone_and_patch`` assigns at least one parameter or names at least one
    source artifact (a verbatim whole-file swap assigns none); ``synthesize``
    names at least one. ``source_artifacts`` are opaque identifiers (a path, a
    digest, a URI), not checked as case-relative: a source may live outside
    the case.
    """

    mode: str
    case_root: Path
    adapter_id: str
    workflow: str
    source_artifacts: tuple[str, ...]
    parameters: tuple[ParameterAssignment, ...]
    requested_by: str

    def __post_init__(self) -> None:
        # A list could be mutated after the duplicate-slot check below ran.
        object.__setattr__(self, "source_artifacts", tuple(self.source_artifacts))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        # A relative root resolves against the directory current at commit
        # time, so one plan could be committed into two places.
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

    ``content`` is embedded in the plan whole, base64-encoded: a rendered
    dictionary is small, and a reviewer or recovery reader needs the bytes,
    not a hash of them. ``content_digest`` is the derived integrity check.
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
class CaseWritePlan:
    """Everything that will happen, reviewable before any of it does.

    The plan holds no execution state. Before-images live in the journal
    (:mod:`omnidriver.core.case_transaction`); before-digests live here,
    because a conflict check is part of what a reviewer approves.
    ``expected_effects`` comes from the ``ResolvedMutation`` and is copied
    onto the committed ``CaseWriteRecord``.
    """

    request: CaseMutationRequest
    files: tuple[RenderedFile, ...]
    semantic_owner_id: str
    stack_identity: str
    created_at: str
    schema_version: int = PLAN_SCHEMA_VERSION
    expected_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A list could be appended to after the duplicate-path check below,
        # changing `plan_digest` after review.
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))
        # Checked here, not only in `from_json`, so a directly constructed
        # plan cannot skirt either check.
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
            "semantic_owner_id": self.semantic_owner_id,
            "stack_identity": self.stack_identity,
            "created_at": self.created_at,
            "expected_effects": list(self.expected_effects),
        }

    @property
    def plan_digest(self) -> str:
        return hashlib.sha256(canonical_json(self._digest_payload()).encode()).hexdigest()

    def _digest_payload(self) -> dict[str, Any]:
        """``to_json()`` with order-irrelevant lists sorted, so only the digest is canonical and a reviewer sees authoring order."""
        payload = self.to_json()
        payload["files"] = sorted(payload["files"], key=lambda f: f["path"])
        payload["request"]["parameters"] = sorted(
            payload["request"]["parameters"],
            key=lambda p: f"{p['document']}::{'.'.join(p['expanded_key_path'])}",
        )
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
            semantic_owner_id=payload["semantic_owner_id"],
            stack_identity=payload["stack_identity"],
            created_at=payload["created_at"],
            schema_version=version,
            expected_effects=tuple(payload["expected_effects"]),
        )


@dataclass(frozen=True)
class CaseWriteRecord:
    """What a committed transaction actually did. Not part of the plan.

    ``parameters`` and ``expected_effects`` are copied from the committed plan
    by ``commit_case_write``; ``describe`` reads them off a staged clone to say
    what a step will change.
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
        # The entries are plain dicts inside a tuple, so freeze them.
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
            # `dict(entry)` unwraps only the outermost proxy; a parameter's
            # nested mappings need `_json_value` to serialize.
            "parameters": [_json_value(entry) for entry in self.parameters],
            "expected_effects": list(self.expected_effects),
        }


@dataclass(frozen=True)
class ResolvedMutation:
    """The semantic owner's answer: concrete addresses and expected effects.

    Pure: produced without reading the case, so a dry run changes nothing.
    The renderer reads; this does not. ``targets`` is consumed by the
    renderer and ``semantic_owner_id`` passes through into ``CaseWritePlan``.
    """

    request: CaseMutationRequest
    targets: tuple[Mapping[str, Any], ...]
    expected_effects: tuple[str, ...]
    semantic_owner_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(_freeze(target) for target in self.targets))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))


def resolve_mutation(driver_context: Any, request: CaseMutationRequest) -> "ResolvedMutation":
    """The stack's resolution of ``request``, refused when its resolver does
    not accept the mode or changes the case tree.

    Purity is checked by the path names under ``request.case_root`` before
    and after; an in-place edit, a write outside the case or a read is not
    caught, and a resolver that reads makes a dry run depend on case state.
    """
    stack = driver_context.stack
    if not stack.implements("resolve_case_mutation"):
        raise stack.refusal("resolve_case_mutation")
    supported = stack.call("get_supported_mutation_modes")
    if request.mode not in supported:
        raise ValueError(
            f"the provider stack {list(stack.ids)} does not support creation "
            f"mode {request.mode!r}; it supports {sorted(supported)}"
        )
    root = Path(request.case_root)
    before = set(root.rglob("*")) if root.is_dir() else set()
    resolved = stack.call("resolve_case_mutation", request, driver_context=driver_context)
    after = set(root.rglob("*")) if root.is_dir() else set()
    if before != after:
        raise ValueError(
            f"resolve_case_mutation() must be pure; {request.adapter_id!r} "
            f"changed {sorted(str(p) for p in before ^ after)}"
        )
    return resolved


def render_mutation(
    driver_context: Any, resolved: "ResolvedMutation", *, snapshot_root: Path, execution_env: Any | None = None,
) -> tuple[RenderedFile, ...]:
    """Every renderer's files for ``resolved``, each refused unless its
    provider declares the file's format and is named as its ``renderer_id``."""
    stack = driver_context.stack
    renderers = stack.implementers("render_case_files")
    if not renderers:
        raise stack.refusal("render_case_files")
    rendered: list[RenderedFile] = []
    for provider in renderers:
        declared = frozenset(provider.get_rendered_formats())
        for file in provider.render_case_files(
            resolved, snapshot_root=snapshot_root, driver_context=driver_context, execution_env=execution_env,
        ):
            if file.format not in declared:
                raise ValueError(
                    f"provider {provider.plugin_id!r} rendered {file.path!r} claiming "
                    f"format {file.format!r}, which it does not declare via "
                    f"get_rendered_formats() (declared: {sorted(declared)})"
                )
            if file.renderer_id != provider.plugin_id:
                raise ValueError(
                    f"provider {provider.plugin_id!r} rendered {file.path!r} with "
                    f"renderer_id {file.renderer_id!r}; a rendered file names the "
                    f"provider that produced it"
                )
            rendered.append(file)
    return tuple(rendered)
