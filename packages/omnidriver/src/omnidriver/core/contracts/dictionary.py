"""Generic dictionary-catalog value objects.

Core owns the shape and the closed ``value_kind`` vocabulary of value shapes (how a value is built, never what it means, so no kind can mean "unchecked"); plugins own the entries, units and ranges."""

from __future__ import annotations

import math
from collections.abc import Mapping as _Mapping, Sequence as _Sequence
from dataclasses import dataclass, field, replace
from numbers import Integral, Real
from typing import Any

from .catalogue_paths import PLACEHOLDER

#: Generic value SHAPES, closed. Adding a member changes what every adapter and
#: renderer must handle; never add one that no declaration uses or one that
#: means "unchecked".
#:
#: The typed lists are distinct from a bare ``list`` because the element type
#: is information a renderer needs (a list of words and a list of scalars are
#: spelled differently); no untyped list is offered. ``dimensioned_scalar``
#: and ``dimensioned_tensor`` pair a magnitude with a seven-exponent dimension
#: vector, and are two kinds because the magnitude's shape differs.
#:
#: ``string`` is text whose native type is text (an openCARP
#: ``String``/``RFile``/``WFile`` parameter, which may be empty or contain
#: spaces, both refused by ``word``). It is never pre-rendered native syntax,
#: such as a vector or a count spelled out as text.
VALUE_KINDS = frozenset({
    "scalar", "integer", "boolean", "word", "enum", "vector3",
    "dimensioned_scalar", "dimensioned_tensor",
    "word_list", "scalar_list", "vector3_list", "integer_list",
    "mapping", "string",
})

#: Element shape for each typed-list kind, reusing the singular check.
_LIST_ELEMENT_KIND = {
    "word_list": "word",
    "scalar_list": "scalar",
    "vector3_list": "vector3",
    "integer_list": "integer",
}



def _finite(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_scalar_like(value: Any) -> tuple[str, ...]:
    if isinstance(value, bool) or not isinstance(value, Real):
        return ("must be a number",)
    return () if _finite(value) else ("must be a finite number",)


def validate_value_shape(kind: str, value: Any) -> tuple[str, ...]:
    """Reasons a value does not fit a declared shape; empty when it fits.

    Returns reasons rather than raising, so a caller can report every bad
    parameter in one pass instead of stopping at the first one. This checks
    generic shape only -- never units, ranges, or a specific entry's
    ``enum_values``; those are the adapter's concern.
    """
    if kind not in VALUE_KINDS:
        return (f"unknown value kind {kind!r}; known kinds are {sorted(VALUE_KINDS)}",)
    if kind == "scalar":
        return _validate_scalar_like(value)
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, Integral):
            return ("must be an integer",)
        return ()
    if kind == "boolean":
        return () if isinstance(value, bool) else ("must be a boolean",)
    if kind == "string":
        # Any text, including empty or with spaces: openCARP's
        # String/RFile/WFile parameters need it; ``word`` refuses both.
        return () if isinstance(value, str) else ("must be a string",)
    if kind in {"word", "enum"}:
        if not isinstance(value, str) or not value:
            return ("must be a non-empty word",)
        return () if value.split() == [value] else ("must contain no whitespace",)
    if kind == "vector3":
        if isinstance(value, (str, bytes)) or not isinstance(value, _Sequence):
            return ("must be three numbers",)
        if len(value) != 3:
            return (f"must be three numbers, not {len(value)}",)
        bad = [i for i, item in enumerate(value) if isinstance(item, bool) or not _finite(item)]
        return (f"components {bad} must be finite numbers",) if bad else ()
    if kind in {"dimensioned_scalar", "dimensioned_tensor"}:
        if not isinstance(value, _Mapping):
            return ("must be a mapping with value and dimensions",)
        reasons = []
        magnitude = value.get("value")
        if "value" not in value:
            reasons.append("missing 'value'")
        elif kind == "dimensioned_scalar":
            reasons.extend(f"'value' {r}" for r in _validate_scalar_like(magnitude))
        else:
            if (
                isinstance(magnitude, (str, bytes))
                or not isinstance(magnitude, _Sequence)
                or not magnitude
            ):
                reasons.append("'value' must be a non-empty sequence of numbers for a tensor")
            else:
                bad = [
                    i for i, item in enumerate(magnitude)
                    if isinstance(item, bool) or not _finite(item)
                ]
                if bad:
                    reasons.append(f"'value' components {bad} must be finite numbers")
        dimensions = value.get("dimensions")
        if dimensions is None:
            reasons.append("missing 'dimensions'")
        elif isinstance(dimensions, (str, bytes)) or not isinstance(dimensions, _Sequence):
            reasons.append("'dimensions' must be seven exponents")
        elif len(dimensions) != 7:
            reasons.append(f"'dimensions' must be seven exponents, not {len(dimensions)}")
        else:
            bad_dims = [i for i, item in enumerate(dimensions) if not _finite(item)]
            if bad_dims:
                reasons.append(f"'dimensions' components {bad_dims} must be finite numbers")
        return tuple(reasons)
    if kind in _LIST_ELEMENT_KIND:
        if isinstance(value, (str, bytes)) or not isinstance(value, _Sequence):
            return ("must be a sequence",)
        element_kind = _LIST_ELEMENT_KIND[kind]
        reasons = []
        for index, item in enumerate(value):
            item_reasons = validate_value_shape(element_kind, item)
            reasons.extend(f"element {index} {r}" for r in item_reasons)
        return tuple(reasons)
    if kind == "mapping":
        # An axis's study value may be one mapping of named parameters rather
        # than a document key's value. Generic shape only; the axis's own
        # `resolve` checks its required keys by name.
        if isinstance(value, (str, bytes)) or not isinstance(value, _Mapping):
            return ("must be a mapping",)
        return ()
    raise AssertionError(f"unhandled value kind {kind!r}")  # pragma: no cover


@dataclass(frozen=True)
class DictEntry:
    driver_path: str
    description: str
    # No default, so a missing declaration is visible; placed before the
    # defaulted fields because a dataclass cannot order them otherwise.
    value_kind: str
    source_refs: tuple[str, ...] = ()
    notes: str = ""
    enum_values: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    required: bool = False
    constraints: tuple[str, ...] = ()
    unit: str = ""
    typical_value: str = ""
    # The value the solver takes when this key is absent. Stated only for a
    # selector whose absence another entry's predicate has to see as that value;
    # ``typical_value`` is what a built case writes, not what an absent key means.
    default: str = ""
    phases: frozenset[str] = frozenset()
    applicable_when: dict[str, str | tuple[str, ...]] = field(default_factory=dict)
    forbidden_when: dict[str, str | tuple[str, ...]] = field(default_factory=dict)
    required_when: dict[str, str | tuple[str, ...]] = field(default_factory=dict)
    mutually_exclusive_with: tuple[str, ...] = ()
    # Inverse of ``mutually_exclusive_with``: naming a sibling here means
    # "if my slot is set, that sibling's slot must be set too". Declare it
    # on every member of the group to make the relation symmetric.
    co_required_with: tuple[str, ...] = ()
    # A dynamic path's declared domain per placeholder, e.g.
    # ``{"<ventKey>": ("lv", "rv")}``. An explicit ``None`` states "open by
    # decision", distinct from a placeholder left out; naming some but not all
    # of an entry's placeholders is refused. An open binding still validates as
    # a word; only a closed domain restricts membership.
    allowed_bindings: dict[str, tuple[str, ...] | None] = field(default_factory=dict)

    @property
    def dynamic_path(self) -> bool:
        """Whether the path names instances of a block: it holds a ``<placeholder>``."""
        return bool(PLACEHOLDER.search(self.driver_path))

    def __post_init__(self) -> None:
        if self.value_kind not in VALUE_KINDS:
            raise ValueError(
                f"{self.driver_path!r} declares value_kind {self.value_kind!r}, "
                f"which is not one of {sorted(VALUE_KINDS)}"
            )
        if self.default and self.enum_values and self.default not in self.enum_values:
            raise ValueError(
                f"{self.driver_path!r} declares default {self.default!r}, "
                f"which is not one of its enum_values"
            )
        if self.allowed_bindings and not self.dynamic_path:
            raise ValueError(
                f"{self.driver_path!r} declares allowed_bindings but its path has "
                f"no placeholder; bindings only apply to a placeholder in the path"
            )
        if self.allowed_bindings:
            placeholders = set(PLACEHOLDER.findall(self.driver_path))
            declared = set(self.allowed_bindings)
            unknown = sorted(declared - placeholders)
            if unknown:
                raise ValueError(
                    f"{self.driver_path!r} declares allowed_bindings for "
                    f"{unknown}, which do not appear in the path"
                )
            undeclared = sorted(placeholders - declared)
            if undeclared:
                raise ValueError(
                    f"{self.driver_path!r} declares allowed_bindings for some "
                    f"of its placeholders but not {undeclared}; a partially "
                    f"declared binding is how an undeclared placeholder went "
                    f"unchecked"
                )
            # `None` is the explicitly-open domain (see the field's own
            # comment above) and is deliberately exempt from this check: it
            # is a stated fact, not an empty one. Only `()` -- a *closed*
            # domain with no members -- can never be satisfied.
            empty = sorted(
                placeholder for placeholder, domain in self.allowed_bindings.items()
                if domain is not None and not domain
            )
            if empty:
                raise ValueError(
                    f"{self.driver_path!r} declares an empty domain for "
                    f"{empty}; a placeholder with no allowed value can never "
                    f"be satisfied"
                )


def build_group(
    defaults: dict[str, Any],
    entries: tuple[DictEntry, ...],
) -> tuple[DictEntry, ...]:
    """Apply group defaults without mutating plugin-owned entry objects."""
    out = []
    for entry in entries:
        changes = {}
        for key, value in defaults.items():
            current = getattr(entry, key)
            if not current:
                changes[key] = value
            elif isinstance(current, dict) and isinstance(value, dict):
                changes[key] = {**value, **current}
        out.append(replace(entry, **changes) if changes else entry)
    return tuple(out)
