"""OpenFOAM dictionary assertions owned by the cardiacFoam adapter tests."""

from __future__ import annotations

import re
from pathlib import Path

from omnidriver.openfoam.mutators import read_foam_entry


def _foam_tokens(value: str) -> list[str]:
    return re.findall(r"[()\[\]]|[^\s()\[\]]+", value)


def foam_values_equal(actual: str, expected: str) -> bool:
    actual_tokens, expected_tokens = _foam_tokens(actual), _foam_tokens(expected)
    if len(actual_tokens) != len(expected_tokens):
        return False
    for got, want in zip(actual_tokens, expected_tokens):
        if got == want:
            continue
        try:
            if float(got) == float(want):
                continue
        except ValueError:
            pass
        return False
    return True


def assert_foam_entry(path, key, expected, *, scope=None) -> None:
    """Assert an OpenFOAM dictionary entry, independent of spelling details."""
    actual = read_foam_entry(Path(path), key, scope=scope)
    assert actual is not None, f"{key!r} not found (scope={scope!r}) in {path}"
    assert foam_values_equal(actual, expected), (
        f"{key!r} (scope={scope!r}) is {actual!r}, expected {expected!r}"
    )
