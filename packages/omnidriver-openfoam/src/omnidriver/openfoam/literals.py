"""Parse and render OpenFOAM's dimensioned-literal and vector-literal text.

Phase 2's "a parameter value is typed data, never rendered text" decision
(``docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md``) asserted:
"Where an adapter currently holds a rendered string, the adapter parses it
when building the request." No such parser was ever written anywhere in this
repository -- ``literals._format_value`` renders typed data *to* text (and
performs the SECURITY.md security checks) but nothing before this module ever
read a dimensioned literal like ``"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"``
back into the ``{"value": ..., "dimensions": (...)}`` shape
``omnidriver.core.contracts.dictionary.validate_value_shape`` requires for a
``dimensioned_scalar``/``dimensioned_tensor`` entry.

OpenFOAM owns this syntax; core must never learn it (core moves bytes and
digests, never dictionary grammar). This module is the one place in this
monorepo that parses or renders it, so a caller two layers up does not have
to re-derive the grammar.

Every real dimensioned literal in this repository (the catalog's own
``typical_value`` strings, the tutorials' own default conductivities, and the
literals real tests pass as overrides) parses here, and every one of them
reproduces the same *value* on a parse -> format -> parse round trip
(``test_literals.py::test_every_real_dimensioned_literal_round_trips``).
Byte-for-byte reproduction of the original spelling is a stronger claim than
that, and does not hold universally: a human-typed literal can pad its
brackets with spaces, or spell an insignificant trailing zero
(``"0.030"`` for the float 0.03) that a canonical re-rendering omits. Finding
F1b already established that comparing values as *text* is the wrong axis
(a requested ``1e-3`` resolves natively to ``0.001``, and rejecting that as
"different" was the defect); the same reasoning applies here; the *value* is
what must round-trip, not the spelling. The raw spelling itself is still kept
as evidence by this module's caller (``omnidriver.cardiacfoam.overrides``
attaches it as a ``ParameterAssignment.evidence_refs`` entry) rather than
discarded, and is what a transitional writer uses verbatim when it has one --
see that module for why.

Vector-literal parsing (``"(x y z)"``) is included for the same reason, on
the same evidence: a real catalog entry (``ecgDomains.<name>.electrodePositions.<electrode>``)
is ``value_kind="vector3"`` but a real caller passes it as already-rendered
text, not a Python tuple. This is the vector3 counterpart of the same gap
Phase 3's decision named for the dimensioned kinds; found while implementing
that decision, not anticipated by it (noted 2026-09-23).

List-literal parsing (``"(a b c)"`` for ``word_list``/``scalar_list``/
``integer_list``, and ``"((x y z) (x y z))"`` for ``vector3_list``) is
included for the same reason again: a real override
(``manufactured_monodomain_pseudo_ecg.py``'s
``verificationModel.checkQuadratureOrders``, ``value_kind="integer_list"``)
is passed as ``"(6 12 24 48)"``, not ``(6, 12, 24, 48)``. Found the same way
as the ``vector3`` gap -- while closing Gap 2 made the surrounding override
batch reach `validate_value_shape` for the first time, this was the next
kind it rejected.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_DIMENSIONED_RE = re.compile(r"^\[(?P<dims>[^\]]*)\]\s*(?P<magnitude>.+)$")
_PAREN_SEQUENCE_RE = re.compile(r"^\((?P<body>.*)\)$")
_VECTOR3_RE = re.compile(r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)$")

#: OpenFOAM's dimension set always names exactly seven exponents (mass,
#: length, time, temperature, quantity, current, luminous intensity).
_DIMENSION_COUNT = 7


def _parse_number(token: str, *, what: str, original: str) -> float:
    try:
        return float(token)
    except ValueError as exc:
        raise ValueError(
            f"{original!r} is not a valid dimensioned literal: {what} "
            f"{token!r} is not a number"
        ) from exc


def _format_number(value: Any) -> str:
    """Canonical text for one magnitude or dimension-exponent component.

    A whole number renders without a decimal point (OpenFOAM dimension
    exponents and many magnitudes are written this way, e.g. ``60`` not
    ``60.0``); anything else uses Python's shortest round-tripping `repr`,
    which reproduces every non-integer magnitude actually found in this
    catalog exactly (``0.1334``, ``-0.5``, ...) -- see the module docstring
    for the one respect in which this is not a universal byte-for-byte
    guarantee (an insignificant trailing zero in the original spelling).
    """
    if isinstance(value, bool):
        raise TypeError("a dimensioned/vector literal component must be a number, not a boolean")
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def parse_dimensioned_literal(text: str) -> dict[str, Any]:
    """Parse ``"[d0 d1 d2 d3 d4 d5 d6] magnitude"`` into the typed shape
    `validate_value_shape` requires for a ``dimensioned_scalar``/
    ``dimensioned_tensor`` entry: ``{"value": <float or tuple of float>,
    "dimensions": <tuple of seven float>}``.

    Handles both magnitude shapes the real catalog declares: a bare scalar
    (``stimulusIntensity``: ``"[0 -3 0 0 0 1 0] 75000"``) and a
    parenthesised tensor (``conductivity``:
    ``"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"``).

    Refuses (``ValueError``), never guesses, a literal that: is not
    bracket-delimited, does not declare exactly seven dimension exponents,
    or whose magnitude is neither a bare number nor a parenthesised,
    non-empty sequence of numbers.
    """
    stripped = text.strip()
    match = _DIMENSIONED_RE.match(stripped)
    if match is None:
        raise ValueError(
            f"{text!r} is not a dimensioned literal; expected "
            f"'[d0 d1 d2 d3 d4 d5 d6] magnitude'"
        )
    dim_tokens = match.group("dims").split()
    if len(dim_tokens) != _DIMENSION_COUNT:
        raise ValueError(
            f"{text!r} declares {len(dim_tokens)} dimension exponent(s), not "
            f"the seven ({_DIMENSION_COUNT}) OpenFOAM's dimension set requires"
        )
    dimensions = tuple(
        _parse_number(token, what="dimension exponent", original=text)
        for token in dim_tokens
    )

    magnitude_text = match.group("magnitude").strip()
    paren = _PAREN_SEQUENCE_RE.match(magnitude_text)
    if paren is not None:
        components = paren.group("body").split()
        if not components:
            raise ValueError(f"{text!r} declares an empty tensor magnitude")
        magnitude: Any = tuple(
            _parse_number(token, what="tensor component", original=text)
            for token in components
        )
    else:
        magnitude = _parse_number(magnitude_text, what="scalar magnitude", original=text)

    return {"value": magnitude, "dimensions": dimensions}


def format_dimensioned_literal(value: Mapping[str, Any]) -> str:
    """Render typed dimensioned data back into OpenFOAM literal text.

    The inverse of `parse_dimensioned_literal`, and -- Phase 2's "a
    parameter value is typed data" decision believed this direction already
    existed in `literals._format_value`. It does not: that function has
    never handled a mapping, and nothing before this module ever produced
    the typed ``{"value", "dimensions"}`` shape to render in the first
    place. See the module docstring on why this does not guarantee a
    byte-identical reproduction of an arbitrary original spelling, only a
    value-identical one.
    """
    dimensions = value["dimensions"]
    magnitude = value["value"]
    dims_text = " ".join(_format_number(d) for d in dimensions)
    if isinstance(magnitude, Sequence) and not isinstance(magnitude, (str, bytes)):
        magnitude_text = "(" + " ".join(_format_number(m) for m in magnitude) + ")"
    else:
        magnitude_text = _format_number(magnitude)
    return f"[{dims_text}] {magnitude_text}"


def parse_vector3_literal(text: str) -> tuple[float, float, float]:
    """Parse ``"(x y z)"`` into three floats.

    This is the same text shape
    ``cardiaccore.workflows.overrides._typed_value`` already parses for its
    own adapter (that module's ``_VECTOR_TEXT``), re-implemented here rather
    than imported: ``omnidriver.cardiaccore`` and ``omnidriver.cardiacfoam``
    must not depend on each other, and this belongs to neither -- it is
    OpenFOAM vector syntax, owned by ``omnidriver-openfoam`` like every
    other literal in this module.
    """
    match = _VECTOR3_RE.match(text.strip())
    if match is None:
        raise ValueError(f"{text!r} is not a '(x y z)' vector literal")
    return tuple(
        _parse_number(token, what="vector component", original=text)
        for token in match.groups()
    )


def format_vector3_literal(value: Sequence[Any]) -> str:
    """The inverse of `parse_vector3_literal`."""
    return "(" + " ".join(_format_number(component) for component in value) + ")"


#: OpenFOAM's ``Switch`` class accepts several case-insensitive spellings
#: for each boolean state (``Switch.C``'s own ``names`` table: false/true,
#: no/yes, off/on, none/any, n/y, f/t, invalid/0-and-1 is not one of these
#: pairs and is refused rather than guessed at). Only the spellings a real
#: override in this repository actually uses (`eikonalAdvectionDiffusionApproach`:
#: ``"false"``/``"true"``) are exercised by this repository's tests, but the
#: full accepted set is included rather than a narrower one invented for
#: just that caller, since a caller passing ``"yes"``/``"no"`` tomorrow is
#: exactly as legitimate and this module should not need to change to admit
#: it.
_SWITCH_TRUE = frozenset({"true", "yes", "on", "y", "t", "1"})
_SWITCH_FALSE = frozenset({"false", "no", "off", "n", "f", "0"})


def parse_boolean_literal(text: str) -> bool:
    """Parse an OpenFOAM ``Switch`` spelling (``"true"``/``"false"``,
    ``"yes"``/``"no"``, ``"on"``/``"off"``, ...) into a Python `bool`.
    """
    normalized = text.strip().lower()
    if normalized in _SWITCH_TRUE:
        return True
    if normalized in _SWITCH_FALSE:
        return False
    raise ValueError(
        f"{text!r} is not a recognised OpenFOAM Switch spelling "
        f"(expected one of {sorted(_SWITCH_TRUE | _SWITCH_FALSE)})"
    )


def format_boolean_literal(value: bool) -> str:
    """The inverse of `parse_boolean_literal`. Canonical spelling only
    (``"true"``/``"false"``) -- rendering every accepted synonym back to
    its own spelling is not this function's job; the caller's original
    spelling, when it must be preserved exactly, is kept as evidence by
    that caller instead (see ``omnidriver.cardiacfoam.overrides``)."""
    return "true" if value else "false"


def _split_top_level_tokens(text: str) -> list[str]:
    """Split OpenFOAM list text ``"(a b c)"`` into top-level tokens,
    honouring a nested parenthesised element (a ``vector3_list``'s own
    ``"(x y z)"`` entries) as one token rather than splitting inside it.
    """
    stripped = text.strip()
    if not (stripped.startswith("(") and stripped.endswith(")")):
        raise ValueError(f"{text!r} is not a parenthesised OpenFOAM list")
    inner = stripped[1:-1]
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in inner:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(f"{text!r} has an unbalanced ')'")
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if depth != 0:
        raise ValueError(f"{text!r} has an unbalanced '('")
    if current:
        tokens.append("".join(current))
    return tokens


def parse_word_list_literal(text: str) -> tuple[str, ...]:
    """Parse ``"(alpha beta)"`` into ``("alpha", "beta")``."""
    return tuple(_split_top_level_tokens(text))


def format_word_list_literal(value: Sequence[str]) -> str:
    return "(" + " ".join(str(item) for item in value) + ")"


def parse_scalar_list_literal(text: str) -> tuple[float, ...]:
    """Parse ``"(1 2.5 3)"`` into ``(1.0, 2.5, 3.0)``."""
    return tuple(
        _parse_number(token, what="scalar list element", original=text)
        for token in _split_top_level_tokens(text)
    )


def format_scalar_list_literal(value: Sequence[Any]) -> str:
    return "(" + " ".join(_format_number(item) for item in value) + ")"


def parse_integer_list_literal(text: str) -> tuple[int, ...]:
    """Parse ``"(6 12 24 48)"`` into ``(6, 12, 24, 48)``."""
    values = []
    for token in _split_top_level_tokens(text):
        number = _parse_number(token, what="integer list element", original=text)
        if not float(number).is_integer():
            raise ValueError(
                f"{text!r} element {token!r} is not an integer"
            )
        values.append(int(number))
    return tuple(values)


def format_integer_list_literal(value: Sequence[Any]) -> str:
    return "(" + " ".join(str(int(item)) for item in value) + ")"


def parse_vector3_list_literal(text: str) -> tuple[tuple[float, float, float], ...]:
    """Parse ``"((1 0 0) (0 1 0))"`` into a tuple of vector3 tuples."""
    return tuple(parse_vector3_literal(token) for token in _split_top_level_tokens(text))


def format_vector3_list_literal(value: Sequence[Sequence[Any]]) -> str:
    return "(" + " ".join(format_vector3_literal(item) for item in value) + ")"

# Moved here from `mutators` 2026-09-25 (consolidation): it is pure -- it
# renders a typed value to dictionary text and applies SECURITY.md's `;`/`#`
# refusals -- and `case_planning`, the writer-free module axes import, needs
# it. Leaving it in `mutators` made that "pure" module depend on the module
# that writes live case files.
def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"

    text = str(value)

    # Override values arrive verbatim from sweep.json and the CLI and are
    # written straight into a case dictionary, so a value carrying a `;` can
    # append a second entry, and a `#`-directive becomes code OpenFOAM will
    # compile and run. Neither is a legitimate scalar override; refuse both
    # rather than trusting the caller. See SECURITY.md.
    if ";" in text or "\n" in text:
        raise ValueError(
            f"override value {text!r} contains a statement separator; "
            "a value may not introduce additional dictionary entries"
        )
    if "#" in text:
        raise ValueError(
            f"override value {text!r} contains an OpenFOAM directive; "
            "directives are not permitted in override values"
        )

    return text
