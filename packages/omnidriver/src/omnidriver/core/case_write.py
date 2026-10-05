"""What a framework-authored case mutation is, before anything is written: its types,
and the two calls (:func:`resolve_mutation`, :func:`render_mutation`) that ask the stack to resolve and render.
Core knows no dictionary syntax; a format owner turns a mutation into bytes and core commits them."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .contracts.dictionary import VALUE_KINDS, validate_value_shape

class CaseKeyNotFound(KeyError):
    """A writer was asked to edit a key or block its document does not hold. The one ``KeyError`` a
    tutorial record's case write turns into a refusal by name; any other is a defect and propagates."""


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


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class RenderedFile:
    """One file's complete proposed content, as its format owner rendered it.

    ``content`` is the whole file: a rendered dictionary is small, and a
    reviewer needs the bytes, not a hash of them.
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


@dataclass(frozen=True)
class CaseWritePlan:
    """Everything that will be written, reviewable before any of it is.

    The plan holds no execution state. ``expected_effects`` comes from the
    ``ResolvedMutation`` and is copied onto the committed ``CaseWriteRecord``.
    """

    request: CaseMutationRequest
    files: tuple[RenderedFile, ...]
    semantic_owner_id: str
    stack_identity: str
    expected_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A list could be appended to after the duplicate-path check below.
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "expected_effects", tuple(self.expected_effects))
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


@dataclass(frozen=True)
class CaseWriteRecord:
    """What a commit wrote: the case-relative paths, and the plan's parameters and expected effects."""

    committed: tuple[str, ...]
    parameters: tuple[ParameterAssignment, ...] = ()
    expected_effects: tuple[str, ...] = ()


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
