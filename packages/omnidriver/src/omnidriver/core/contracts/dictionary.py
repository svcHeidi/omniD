"""Generic dictionary-catalog value objects.

Core owns this shape and its closed ``value_kind`` vocabulary of generic
value *shapes* -- how a value is built, never what it means, so no kind can
mean "unchecked". Plugins own the entries; units, ranges and physical
interpretation are the adapter's.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping as _Mapping, Sequence as _Sequence
from dataclasses import dataclass, field, replace
from numbers import Integral, Real
from typing import Any

#: Generic value SHAPES, closed. Adding a member here is a real change to what
#: every adapter and renderer must handle; do not add one that no declaration
#: uses, and do not add a member that means "unchecked" -- that is exactly
#: the hole this vocabulary closes.
#:
#: The typed-list members (``word_list``, ``scalar_list``, ``vector3_list``,
#: ``integer_list``) are kept distinct from a bare ``list`` because the
#: element type is information a renderer needs -- a list of words and a
#: list of scalars are spelled differently in every format this framework
#: has. No declaration needs an untyped list, so one is not offered.
#:
#: ``dimensioned_scalar`` and ``dimensioned_tensor`` name a magnitude paired
#: with a seven-exponent physical-dimension vector -- a dimensional-analysis
#: concept independent of any file format. They are two kinds, not one, for
#: the same reason as the typed lists: the magnitude's shape differs (one
#: number vs. several).
#:
#: ``tensor9`` and ``dictionary`` are deliberately absent: no current
#: ``DictEntry`` declaration has that shape, and a kind nothing uses is not
#: added.
#:
#: ``string`` is text whose *native type is text*: an openCARP
#: ``String``/``RFile``/``WFile`` parameter, which may be empty or contain
#: spaces, both of which ``word`` refuses. It is never a pre-rendered native
#: literal -- a vector, a list, a dimensioned value or a count spelled out as
#: text; a declaration that reaches for ``string`` to carry rendered syntax
#: is the defect, not this kind. Its only user today is omnidriver-opencarp's
#: catalog.
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

_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_]*>")


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
        # A tutorial-record axis's own study value is not always one of the
        # shapes above -- an S1-S2 protocol axis takes one mapping of named
        # parameters as its single study value, not a document key's value.
        # Generic shape only: arbitrary keys/values, never checked against a
        # specific protocol's required keys (the axis's own `resolve` does
        # that, by name).
        if isinstance(value, (str, bytes)) or not isinstance(value, _Mapping):
            return ("must be a mapping",)
        return ()
    raise AssertionError(f"unhandled value kind {kind!r}")  # pragma: no cover


@dataclass(frozen=True)
class DictEntry:
    driver_path: str
    description: str
    # No default: a default here (previously "literal", then "word") hides a
    # missing declaration from grep and review, since a field that always has
    # some value looks declared either way. Placed before every field that
    # still defaults, since a dataclass field with no default cannot follow
    # one that has one.
    value_kind: str
    source_refs: tuple[str, ...] = ()
    notes: str = ""
    enum_values: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    dynamic_path: bool = False
    required: bool = False
    constraints: tuple[str, ...] = ()
    unit: str = ""
    typical_value: str = ""
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
    # ``{"<ventKey>": ("lv", "rv")}``. Most placeholders here are open-ended,
    # case-author-chosen identifiers with no closed domain, and leaving this
    # empty is fine for those. Where an entry instead maps a placeholder to
    # ``None`` explicitly, that states "open by decision", not "unaudited" --
    # distinct from a key that is merely absent. Naming some but not all of
    # an entry's placeholders is refused either way: a partial declaration is
    # how an undeclared placeholder goes unchecked. A binding against an open
    # domain still validates as a word and still passes every other syntax
    # refusal a written key must (`omnidriver.openfoam.mutators`); only a
    # closed domain further restricts membership.
    allowed_bindings: dict[str, tuple[str, ...] | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.value_kind not in VALUE_KINDS:
            raise ValueError(
                f"{self.driver_path!r} declares value_kind {self.value_kind!r}, "
                f"which is not one of {sorted(VALUE_KINDS)}"
            )
        # `_PLACEHOLDER` (`<[A-Za-z][A-Za-z0-9_]*>`) does not match a
        # placeholder spelled `<_x>` or `<x-y>`; not widened here since
        # `specs/validation.py`'s `_predicate_matches` and
        # `dict_builder.py`'s own copy would need to move together.
        has_placeholder = bool(_PLACEHOLDER.search(self.driver_path))
        if has_placeholder and not self.dynamic_path:
            raise ValueError(
                f"{self.driver_path!r} contains a placeholder but does not "
                f"declare dynamic_path=True"
            )
        if self.dynamic_path and not has_placeholder:
            raise ValueError(
                f"{self.driver_path!r} declares dynamic_path=True but "
                f"contains no placeholder for it to expand"
            )
        if self.allowed_bindings and not self.dynamic_path:
            raise ValueError(
                f"{self.driver_path!r} declares allowed_bindings but is not a "
                f"dynamic_path entry; bindings only apply to a placeholder in "
                f"the path"
            )
        if self.allowed_bindings:
            placeholders = set(_PLACEHOLDER.findall(self.driver_path))
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
