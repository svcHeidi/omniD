"""Generic dictionary-catalog value objects.

The core owns this shape and its generic constraint vocabulary. Individual
plugins own the entries and document-specific catalogues built from it.

``value_kind`` is a closed vocabulary of generic value *shapes* -- how a value
is built, never what it means. No units, no ranges, no physical
interpretation: those are the adapter's, supplied only where domain evidence
justifies them, through ``unit`` and the applicability maps below.

Closed 2026-09-22 (Phase 2, Task 4). The previous default was the string
``"literal"``, which said nothing and was checked by nothing, so an adapter's
own value check was the only barrier -- and it accepted ``nan`` for a scalar
and any non-empty string for a vector (audit finding S1). See
``docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md`` Task 4 for
the full migration evidence: 258 declarations were surveyed before this
vocabulary was fixed, and every one of them was migrated to a kind that
describes its actual shape, with no residual "unchecked" escape hatch.
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
#: uses (see the plan's Task 4 instructions) and do not add a member that
#: means "unchecked" -- that is exactly the hole this vocabulary closes.
#:
#: The typed-list members (``word_list``, ``scalar_list``, ``vector3_list``,
#: ``integer_list``) are kept distinct from a bare ``list`` because the
#: element type is information a renderer needs (a list of words and a list
#: of scalars are spelled differently in every format this framework has),
#: and a bare ``list`` is not what any current declaration means. No
#: declaration currently needs a bare, untyped list, so one is not offered.
#:
#: ``dimensioned_scalar`` and ``dimensioned_tensor`` name a magnitude paired
#: with a seven-exponent physical-dimension vector -- a dimensional-analysis
#: concept older than and independent of OpenFOAM, not a file format. They
#: replace the previous ``dimensioned_scalar_literal`` and
#: ``dimensioned_tensor_literal``, whose ``_literal`` suffix named a
#: rendered-text format rather than a shape (see the module docstring on
#: layering). Kept as two kinds, not one, for the same reason as the typed
#: lists: the magnitude's shape differs (one number vs. several).
#:
#: ``tensor9`` and ``dictionary`` were in the plan's first proposal for this
#: vocabulary and are deliberately absent here: no current ``DictEntry``
#: declaration has that shape, and the plan's own instructions are not to add
#: a kind nothing uses.
VALUE_KINDS = frozenset({
    "scalar", "integer", "boolean", "word", "enum", "vector3",
    "dimensioned_scalar", "dimensioned_tensor",
    "word_list", "scalar_list", "vector3_list", "integer_list",
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
    raise AssertionError(f"unhandled value kind {kind!r}")  # pragma: no cover


@dataclass(frozen=True)
class DictEntry:
    driver_path: str
    description: str
    # Mandatory since 2026-09-23 (R2 finding 8). It defaulted to "literal",
    # which said nothing, then to "word" once that vocabulary closed --
    # "word" says something specific and can be WRONG, and three production
    # entries silently declared it by omission
    # ($ELECTRO_MODEL_COEFFS.ecgDomains.<name>.sampling.{start,end,deltaT},
    # each really a "scalar"). A `grep` for `value_kind=` cannot find an
    # entry that omits it, which is how they were missed; a mandatory field
    # cannot be missed the same way. Placed right after `description` --
    # before every field that still defaults -- because a dataclass field
    # with no default cannot follow one that has one; every call site here
    # already uses keyword arguments, so the reorder changes no call site.
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
    # ``{"<ventKey>": ("lv", "rv")}``. Most placeholders in this catalog
    # (``<name>``, ``<electrode>``, ``<region_name>``, ...) are open-ended,
    # case-author-chosen instance identifiers with no closed domain to
    # declare. Leaving `allowed_bindings` entirely empty (the default) for
    # such an entry is still accepted -- there is nothing to check for an
    # open identifier that is never even named here -- but
    # `omnidriver.cardiacfoam.dict_entries_catalog`'s ecgDomains/
    # conductionNetworkDomains/domainCouplings entries instead declare it
    # explicitly, with ``None`` as the placeholder's domain:
    #
    #     allowed_bindings={"<name>": None}
    #
    # Corrected 2026-09-23 (Phase 3, the decision closing Task 2's Gap 2).
    # ``None`` and "key absent" both mean "no closed domain", so neither
    # constrains what value can bind -- but they are not the same STATEMENT.
    # An entry that omits the key says nothing about the placeholder; an
    # entry that maps it to ``None`` says, explicitly, "this is open, and
    # that was decided, not overlooked". Audit finding S1 was that nothing
    # was declared for ``<ventKey>`` at all; the fix docstring above already
    # distinguished "no closed domain to declare" from "unchecked" for the
    # open case, but had no way to WRITE that distinction down -- every
    # open placeholder was, textually, indistinguishable from one nobody had
    # audited yet. A caller resolving a binding against an explicitly open
    # domain still validates it as a word (non-empty, no whitespace) and
    # still applies every other syntax refusal a written key must pass
    # (`;`/`#`/newline -- see `omnidriver.openfoam.mutators`); only a fully
    # *closed* domain additionally restricts membership. What is refused
    # unconditionally, for both an open and a closed domain, is still a
    # *partial* declaration: naming some of an entry's placeholders (open or
    # closed) and silently omitting a sibling, which is how ``<ventKey>``
    # accepted ``"banana"`` while a sibling placeholder went unchecked
    # (audit finding S1).
    allowed_bindings: dict[str, tuple[str, ...] | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.value_kind not in VALUE_KINDS:
            raise ValueError(
                f"{self.driver_path!r} declares value_kind {self.value_kind!r}, "
                f"which is not one of {sorted(VALUE_KINDS)}"
            )
        # R2 finding 12: three one-line guards, latent on the 258 production
        # declarations R2 scanned (zero instances today) but cheap to close
        # regardless. `_PLACEHOLDER` is `<[A-Za-z][A-Za-z0-9_]*>` and so
        # cannot see a placeholder spelled `<_x>` or `<x-y>` -- reported as a
        # known, separate gap rather than widened here, since no current
        # declaration is affected and widening it is a larger, cross-module
        # change (specs/validation.py's `_predicate_matches` and
        # `dict_builder.py`'s own `_PLACEHOLDER_RE` copy would need to move
        # together, not be fixed one at a time).
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
