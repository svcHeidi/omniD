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

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

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
            "unit": self.unit,
            "evidence_refs": list(self.evidence_refs),
        }


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
