"""OpenFOAM cannot lex a bare token that starts with a digit but is not a
number: `dimension 3D;` raises a FatalIOError ("expected word, found label 3").
Tutorials write `dimension "3D";`. The emitter must do the same, and must NOT
quote anything else -- quoting a scalar, vector or dimension set would break
dictionaries that work today.
"""

from __future__ import annotations

import pytest

from omnidriver.openfoam.dict_builder import _openfoam_value_token


@pytest.mark.parametrize("value", ["3D", "1D", "2D", "3Dfoo"])
def test_a_word_starting_with_a_digit_is_quoted(value):
    assert _openfoam_value_token(value) == f'"{value}"'


@pytest.mark.parametrize(
    "value",
    [
        "0.5", "1e-5", "-3", "140000", "1.0E+06", ".5", "+2",   # numbers
        "epicardialCells", "TNNP", "godunov", "yes", "no",       # plain words
        "(1 0 0)", "(bath organ)",                               # lists/vectors
        "[ -1 -3 3 0 0 2 0 ] ( 0.11 0 0 )",                      # dimension set
        '"3D"',                                                  # already quoted
        "",                                                      # empty
    ],
)
def test_everything_else_is_left_untouched(value):
    assert _openfoam_value_token(value) == value
