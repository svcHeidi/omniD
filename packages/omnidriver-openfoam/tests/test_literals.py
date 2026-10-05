"""`omnidriver.openfoam.literals`: the text OpenFOAM reads for a typed value, and the list literals a record reads back."""

from __future__ import annotations

import pytest

from omnidriver.openfoam.literals import (
    CONTAINER_FORMATTERS,
    format_dimensioned_literal,
    format_scalar_list_literal,
    format_vector3_list_literal,
    format_vector3_literal,
    list_elements,
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


def test_a_counted_list_reads_as_its_elements():
    """OpenFOAM writes a list with its element count first, as 1DgraphToFoam writes a graph's edges."""
    assert list_elements("2\n(\n4(0 1 0.5 1)\n4(1 2 0.5 1)\n)") == ["4(0 1 0.5 1)", "4(1 2 0.5 1)"]
    assert parse_scalar_list_literal("4(0 1 0.5 1)") == (0.0, 1.0, 0.5, 1.0)
    assert parse_vector3_list_literal("1((1 0 0))") == ((1.0, 0.0, 0.0),)


def test_list_elements_need_no_space_between_them():
    assert list_elements("((0 1 1 1)(1 2 1 1))") == ["(0 1 1 1)", "(1 2 1 1)"]
    assert list_elements("2(4(0 1 1 1)4(1 2 1 1))") == ["4(0 1 1 1)", "4(1 2 1 1)"]


def test_a_uniform_list_reads_as_its_copies():
    assert list_elements("2{100}") == ["100", "100"]
    assert list_elements("2 {(0 0 1)}") == ["(0 0 1)", "(0 0 1)"]
    assert parse_scalar_list_literal("3{0.5}") == (0.5, 0.5, 0.5)


def test_a_count_that_is_not_the_number_of_elements_is_refused():
    with pytest.raises(ValueError, match="counts 3 elements but holds 2"):
        list_elements("3(1 2)")


def test_a_malformed_list_literal_is_refused():
    with pytest.raises(ValueError, match="list"):
        parse_scalar_list_literal("1 2 3")


def test_every_container_kind_has_a_formatter_and_boolean_has_none():
    assert set(CONTAINER_FORMATTERS) == {
        "dimensioned_scalar", "dimensioned_tensor", "vector3", "word_list", "scalar_list",
        "integer_list", "vector3_list",
    }


def test_switch_reads_exactly_the_spellings_switch_c_parses():
    from omnidriver.openfoam.literals import BOOLEAN_WORDS, switch_value

    for word in ("true", "yes", "on", "any", "t", "y", "1"):
        assert switch_value(word) is True, word
    for word in ("false", "no", "off", "none", "f", "n", "0"):
        assert switch_value(word) is False, word
    for word in ("True", "YES", "maybe", "", "2"):
        assert switch_value(word) is None, word
    assert switch_value('"yes"') is True and switch_value(0) is False and switch_value(3) is True
    assert switch_value(True) is True and switch_value(None) is None
    assert set(BOOLEAN_WORDS) == {"true", "false", "yes", "no", "on", "off"}
