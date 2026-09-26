"""Unit normalisation: a small declared table, nothing inferred.

Each unit maps to (dimension, factor in the dimension's smallest listed
unit). The factors are integers, so a conversion between listed units is one
multiply and one divide. A unit outside the table is refused by name, and
so is a conversion between dimensions. Spellings are ASCII (``us``, ``um``);
a reader declares one of these strings and a request writes one.
Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md §2.
"""
from __future__ import annotations

from typing import Final

from .errors import UnitError

UNITS: Final[dict[str, tuple[str, int]]] = {
    "s": ("time", 1_000_000),
    "ms": ("time", 1_000),
    "us": ("time", 1),
    "m": ("length", 1_000_000),
    "cm": ("length", 10_000),
    "mm": ("length", 1_000),
    "um": ("length", 1),
}


def dimension_of(unit: str) -> str:
    try:
        return UNITS[unit][0]
    except (KeyError, TypeError):
        raise UnitError(f"unit {unit!r} is not in the unit table; known: {sorted(UNITS)}") from None


def check_convertible(from_unit: str, to_unit: str) -> None:
    source, target = dimension_of(from_unit), dimension_of(to_unit)
    if source != target:
        raise UnitError(f"cannot convert {from_unit!r} ({source}) to {to_unit!r} ({target})")


def convert(value: float, from_unit: str, to_unit: str) -> float:
    check_convertible(from_unit, to_unit)
    return value * UNITS[from_unit][1] / UNITS[to_unit][1]
