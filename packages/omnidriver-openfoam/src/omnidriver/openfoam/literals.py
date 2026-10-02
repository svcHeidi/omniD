"""Parse and render OpenFOAM's dimensioned-, vector- and list-literal text.

OpenFOAM owns this syntax; core must never learn it. This is the one place in
the monorepo that parses or renders it.
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

    A whole number renders without a decimal point (e.g. ``60`` not
    ``60.0``); otherwise uses Python's shortest round-tripping `repr`. This
    reproduces the *value*, not necessarily the original spelling -- an
    insignificant trailing zero (``"0.030"`` for ``0.03``) is not preserved.
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

    The inverse of `parse_dimensioned_literal`. Reproduces the *value* on a
    round trip, not necessarily the original spelling -- see `_format_number`.
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

    Re-implemented rather than shared with ``cardiaccore.workflows.overrides``'s
    own parser: ``omnidriver.cardiaccore`` and ``omnidriver.cardiacfoam`` must
    not depend on each other, and this is OpenFOAM vector syntax, owned here.
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


#: OpenFOAM's ``Switch`` class accepts several case-insensitive spellings per
#: boolean state (``Switch.C``'s own ``names`` table: false/true, no/yes,
#: off/on, none/any, n/y, f/t, and the bare digits 0/1).
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
    """Split ``"(a b c)"`` into top-level tokens, keeping a nested ``"(x y z)"`` element (``vector3_list``) as one token."""
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

def _as_comparable_text(text: str):
    """Parse one native scalar/word/vector spelling into a comparable value.

    Returns a float for a number, a bool for an OpenFOAM boolean word, a tuple
    of floats for a parenthesised or unparenthesised whitespace-separated
    vector (``blockMeshDict``'s hex-cell-counts convention omits the
    parentheses), and the stripped text otherwise.
    """
    stripped = text.strip().rstrip(";").strip()
    if not stripped:
        return None
    if stripped in {"true", "yes", "on"}:
        return True
    if stripped in {"false", "no", "off"}:
        return False
    if stripped.startswith("(") and stripped.endswith(")"):
        parts = stripped[1:-1].split()
        try:
            return tuple(float(part) for part in parts)
        except ValueError:
            return stripped
    parts = stripped.split()
    if len(parts) > 1:
        try:
            return tuple(float(part) for part in parts)
        except ValueError:
            return stripped
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _as_comparable(value: Any):
    """Parse a requested value into a comparable one, dispatching on the
    Python type in hand rather than round-tripping through ``str()``
    (``str([1, 2, 3])`` is not the OpenFOAM vector spelling ``"(1 2 3)"``).

    A number becomes a ``float``, an OpenFOAM boolean word or a Python
    ``bool`` stays a ``bool``, a list/tuple or vector string becomes a tuple
    of floats, and anything else is compared as text.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        try:
            return tuple(float(item) for item in value)
        except (TypeError, ValueError):
            return tuple(value)
    if isinstance(value, str):
        return _as_comparable_text(value)
    return value


def values_agree(requested: Any, current: str | None) -> bool:
    """Whether the value a case holds is the one requested, compared as
    parsed values rather than text (a requested ``1e-3`` may read back as
    ``0.001``).

    Deliberately not a tolerance: two different values are never called
    equal. An unparseable or absent value is a non-match, never a passed
    check.
    """
    if current is None:
        return False
    left = _as_comparable(requested)
    right = _as_comparable_text(current)
    if left is None or right is None:
        return False
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


# Kept out of `mutators` (which writes live case files) because the
# writer-free `case_planning` module needs this pure rendering step too.
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
