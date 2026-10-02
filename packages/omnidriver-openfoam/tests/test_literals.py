"""`omnidriver.openfoam.literals`: the text OpenFOAM reads for a typed value, and the list literals a record reads back."""

from __future__ import annotations

import pytest

from omnidriver.openfoam.literals import (
    CONTAINER_FORMATTERS,
    format_dimensioned_literal,
    format_scalar_list_literal,
    format_vector3_list_literal,
    format_vector3_literal,
    parse_scalar_list_literal,
    parse_vector3_list_literal,
    parse_vector3_literal,
)


@pytest.mark.parametrize("value,text", [
    ({"value": 60.0, "dimensions": (0, 0, -0.5, 0, 0, 0, 0)}, "[0 0 -0.5 0 0 0 0] 60"),
    (
        {"value": (0.1334, 0, 0, 0.01761, 0, 0.01761), "dimensions": (-1, -3, 3, 0, 0, 2, 0)},
        "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.01761 0 0.01761)",
    ),
    ({"value": 2.0, "dimensions": (0, 1, -1, 0, 0, 0, 0)}, "[0 1 -1 0 0 0 0] 2"),
])
def test_a_dimensioned_value_is_rendered_in_openfoams_spelling(value, text):
    assert format_dimensioned_literal(value) == text


@pytest.mark.parametrize("text", ["(1 2 3)", "(-0.02 -0.28 -0.07)", "(0 0 0)"])
def test_a_vector3_literal_round_trips_byte_for_byte(text):
    assert format_vector3_literal(parse_vector3_literal(text)) == text


@pytest.mark.parametrize("text", ["1 2 3", "(1 2)", "(1 2 x)"])
def test_a_malformed_vector3_literal_is_refused(text):
    with pytest.raises(ValueError, match="vector|number"):
        parse_vector3_literal(text)


def test_scalar_and_vector3_list_literals_round_trip_byte_for_byte():
    assert format_scalar_list_literal(parse_scalar_list_literal("(1 2 3)")) == "(1 2 3)"
    text = "((1 0 0) (0 1 0))"
    assert format_vector3_list_literal(parse_vector3_list_literal(text)) == text


def test_a_malformed_list_literal_is_refused():
    with pytest.raises(ValueError, match="list"):
        parse_scalar_list_literal("1 2 3")


def test_every_container_kind_has_a_formatter_and_boolean_has_none():
    assert set(CONTAINER_FORMATTERS) == {
        "dimensioned_scalar", "dimensioned_tensor", "vector3", "word_list", "scalar_list",
        "integer_list", "vector3_list",
    }
