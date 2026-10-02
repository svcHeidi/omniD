"""Parse and render OpenFOAM's vector- and list-literal text, and compare values.

OpenFOAM owns this syntax; core must never learn it. This is the one place in
the monorepo that parses or renders it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_VECTOR3_RE = re.compile(r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)$")

#: Every spelling ``Foam::Switch::parse`` (OpenFOAM v2412, ``Switch.C``) reads,
#: case-sensitively: ``none`` is false and ``any`` is true.
SWITCH_VALUES: dict[str, bool] = {
    "false": False, "no": False, "off": False, "none": False, "f": False, "n": False, "0": False,
    "true": True, "yes": True, "on": True, "any": True, "t": True, "y": True, "1": True,
}

#: The spellings of a Switch that cannot be anything else in untyped text,
#: where ``t``, ``n``, ``none`` and ``any`` are ordinary words.
BOOLEAN_WORDS: dict[str, bool] = {
    word: SWITCH_VALUES[word] for word in ("true", "false", "yes", "no", "on", "off")
}


def switch_value(value: Any) -> bool | None:
    """The bool a ``Switch`` reads ``value`` as: a bool, a nonzero label, or a
    word (possibly quoted) ``Switch.C`` accepts. ``None`` for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if value is None:
        return None
    return SWITCH_VALUES.get(str(value).strip().strip("\"'"))


def _parse_number(token: str, *, what: str, original: str) -> float:
    try:
        return float(token)
    except ValueError as exc:
        raise ValueError(
            f"{original!r} is not a valid literal: {what} "
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
    """Parse ``"(x y z)"`` into three floats."""
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
    if stripped in BOOLEAN_WORDS:
        return BOOLEAN_WORDS[stripped]
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


#: Typed container value -> OpenFOAM text, per ``value_kind``. ``boolean`` is
#: absent on purpose: ``_format_value`` already renders a Python ``bool``.
CONTAINER_FORMATTERS = {
    "dimensioned_scalar": format_dimensioned_literal,
    "dimensioned_tensor": format_dimensioned_literal,
    "vector3": format_vector3_literal,
    "word_list": format_word_list_literal,
    "scalar_list": format_scalar_list_literal,
    "integer_list": format_integer_list_literal,
    "vector3_list": format_vector3_list_literal,
}


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
