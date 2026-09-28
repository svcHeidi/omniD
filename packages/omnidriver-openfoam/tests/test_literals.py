"""Round-trip proof for `omnidriver.openfoam.literals`.

Every dimensioned literal actually found in this repository's real catalog,
tutorial defaults, and tests -- not an invented fixture -- parses and, on a
parse -> format -> parse round trip, reproduces the same value.
"""

from __future__ import annotations

import pytest

from omnidriver.openfoam.literals import (
    format_boolean_literal,
    format_dimensioned_literal,
    format_integer_list_literal,
    format_scalar_list_literal,
    format_vector3_list_literal,
    format_vector3_literal,
    format_word_list_literal,
    parse_boolean_literal,
    parse_dimensioned_literal,
    parse_integer_list_literal,
    parse_scalar_list_literal,
    parse_vector3_list_literal,
    parse_vector3_literal,
    parse_word_list_literal,
)

# Every dimensioned literal this repository actually writes as an OVERRIDE
# VALUE (not pre-existing fixture *file content*, which this module's parser
# never sees -- that text is read by mutators.py's line scanner instead).
# Each is tagged with where it was found (`grep -rhoE
# '\[[^]]*\][ ]*\(?[-0-9. ]+\)?' across packages/omnidriver-cardiacfoam,
# cross-checked by hand against its surrounding context).
REAL_DIMENSIONED_LITERALS = (
    # dict_entries_catalog.py DictEntry.typical_value (conductivity /
    # conductivityIntracellular, monodomain + bidomain groups)
    "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.01761 0 0.01761)",
    # dict_entries_catalog.py DictEntry.typical_value (c0)
    "[0 0 -0.5 0 0 0 0] 60",
    # dict_entries_catalog.py DictEntry.typical_value (conductivityExtracellular)
    "[-1 -3 3 0 0 2 0] (0.2668 0 0 0.03521 0 0.03521)",
    # cable1DCVConvergence's native default conductivity (records/
    # cable_1d_cv_convergence.py)
    "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.1334 0 0.1334)",
    # cable1DRestitution's native default conductivity (records/
    # cable_1d_restitution.py)
    "[-1 -3 3 0 0 2 0] (2.3 0 0 2.3 0 2.3)",
    # tests/test_dict_entries_catalog.py::
    # test_apply_electro_property_overrides_updates_dimensioned_and_dynamic_entries
    "[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)",
    "[0 -3 0 0 0 1 0] 75000",
    # tests/test_manufactured_monodomain_pseudo_ecg_tet.py::
    # test_conductivity_shorthand_updates_monodomain_tensor
    "[-1 -3 3 0 0 2 0] (0.1 -0.01 -0.02 0.12 -0.013 0.04)",
    # tests/test_validation.py (purkinjeCV override)
    "[0 1 -1 0 0 0 0] 4.2",
    # tests/test_override_round_trip.py's _VALUES fixture (pre-existing;
    # exercised by that module's whole-catalog sweep, not invented here)
    "[0 0 0 0 0 0 0] (1 0 0 1 0 1)",
)

# Real literals found (same provenance as above) that do NOT survive a
# byte-for-byte round trip. A float cannot distinguish "2" from "2.0", or
# "0.03" from "0.030" -- this repository's own real literals spell a
# whole-number magnitude both ways ("60"/"75000" vs "2.0"/"1.0"), so no
# universal renderer satisfies both; comparing spellings, not values, is the
# wrong axis. Every one of these still round-trips at the VALUE level
# (test_every_real_dimensioned_literal_round_trips_at_the_value_level).
KNOWN_BYTE_ROUND_TRIP_EXCEPTIONS = (
    # tests/test_dict_builder.py (purkinjeCV override): whole-number
    # magnitude spelled with an explicit ".0".
    "[0 1 -1 0 0 0 0] 2.0",
    # tests/test_override_round_trip.py's _VALUES fixture: same.
    "[0 0 0 0 0 0 0] 1.0",
    # tests/test_manufactured_eikonal_ecg_tet.py::
    # test_tet_apply_case_forwards_conductivity_and_advection_approach:
    # padded brackets AND an insignificant trailing zero ("0.030").
    "[ -1 -3 3 0 0 2 0 ] (0.111 0 0 0.122 0 0.030)",
)


@pytest.mark.parametrize("text", REAL_DIMENSIONED_LITERALS + KNOWN_BYTE_ROUND_TRIP_EXCEPTIONS)
def test_every_real_dimensioned_literal_parses(text):
    value = parse_dimensioned_literal(text)
    assert set(value) == {"value", "dimensions"}
    assert len(value["dimensions"]) == 7


@pytest.mark.parametrize("text", REAL_DIMENSIONED_LITERALS)
def test_every_real_dimensioned_literal_round_trips_byte_for_byte(text):
    assert format_dimensioned_literal(parse_dimensioned_literal(text)) == text


@pytest.mark.parametrize("text", REAL_DIMENSIONED_LITERALS + KNOWN_BYTE_ROUND_TRIP_EXCEPTIONS)
def test_every_real_dimensioned_literal_round_trips_at_the_value_level(text):
    """Holds even for the known byte-exceptions above: comparing spellings, not values, is the wrong axis."""
    once = parse_dimensioned_literal(text)
    twice = parse_dimensioned_literal(format_dimensioned_literal(once))
    assert twice == once


def test_the_known_exceptions_really_do_differ_only_insignificantly():
    """Pins exactly what each ``format(parse(text)) != text`` difference is."""
    assert (
        format_dimensioned_literal(parse_dimensioned_literal("[0 1 -1 0 0 0 0] 2.0"))
        == "[0 1 -1 0 0 0 0] 2"
    )
    assert (
        format_dimensioned_literal(parse_dimensioned_literal("[0 0 0 0 0 0 0] 1.0"))
        == "[0 0 0 0 0 0 0] 1"
    )
    assert (
        format_dimensioned_literal(
            parse_dimensioned_literal("[ -1 -3 3 0 0 2 0 ] (0.111 0 0 0.122 0 0.030)")
        )
        == "[-1 -3 3 0 0 2 0] (0.111 0 0 0.122 0 0.03)"
    )


@pytest.mark.parametrize("text,reason", [
    ("-1 -3 3 0 0 2 0] (0.2 0 0)", "dimensioned literal"),
    ("[-1 -3 3 0 0 2] (0.2 0 0)", "seven"),
    ("[-1 -3 3 0 0 2 0 1] (0.2 0 0)", "seven"),
    ("[-1 -3 3 0 0 2 0]", "dimensioned literal"),
    ("[-1 -3 3 0 0 2 0] ()", "empty"),
    ("[-1 -3 3 0 0 2 0] banana", "not a number"),
    ("[-1 banana 3 0 0 2 0] 1.0", "not a number"),
])
def test_a_malformed_literal_is_refused_not_guessed(text, reason):
    with pytest.raises(ValueError, match=reason):
        parse_dimensioned_literal(text)


@pytest.mark.parametrize("value,text", [
    ({"value": 60.0, "dimensions": (0, 0, -0.5, 0, 0, 0, 0)}, "[0 0 -0.5 0 0 0 0] 60"),
    (
        {"value": (0.1334, 0, 0, 0.01761, 0, 0.01761), "dimensions": (-1, -3, 3, 0, 0, 2, 0)},
        "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.01761 0 0.01761)",
    ),
])
def test_format_produces_the_expected_openfoam_spelling(value, text):
    assert format_dimensioned_literal(value) == text


# --- vector3 literal: a real catalog entry
# ($ELECTRO_MODEL_COEFFS.ecgDomains.<name>.electrodePositions.<electrode>) is
# value_kind="vector3", and a real caller passes it as already-rendered text
# ("(1 2 3)"), not a Python tuple. ---


@pytest.mark.parametrize("text", [
    "(1 2 3)",
    "(-0.02 -0.28 -0.07)",
    "(0 0 0)",
])
def test_a_real_vector3_literal_round_trips_byte_for_byte(text):
    assert format_vector3_literal(parse_vector3_literal(text)) == text


def test_a_malformed_vector3_literal_is_refused():
    with pytest.raises(ValueError, match="vector"):
        parse_vector3_literal("1 2 3")
    with pytest.raises(ValueError, match="vector"):
        parse_vector3_literal("(1 2)")


# --- list literals: a real override
# (manufactured_monodomain_pseudo_ecg.py's
# verificationModel.checkQuadratureOrders, value_kind="integer_list") is
# passed as "(6 12 24 48)", not a Python tuple. ---


def test_a_real_integer_list_literal_round_trips_byte_for_byte():
    text = "(6 12 24 48)"
    assert format_integer_list_literal(parse_integer_list_literal(text)) == text


def test_a_word_list_literal_round_trips_byte_for_byte():
    text = "(alpha beta)"
    assert format_word_list_literal(parse_word_list_literal(text)) == text


def test_a_scalar_list_literal_round_trips_byte_for_byte():
    text = "(1 2 3)"
    assert format_scalar_list_literal(parse_scalar_list_literal(text)) == text


def test_a_vector3_list_literal_round_trips_byte_for_byte():
    text = "((1 0 0) (0 1 0))"
    assert format_vector3_list_literal(parse_vector3_list_literal(text)) == text


def test_an_integer_list_literal_with_a_non_integer_element_is_refused():
    with pytest.raises(ValueError, match="not an integer"):
        parse_integer_list_literal("(1 2.5 3)")


def test_a_malformed_list_literal_is_refused():
    with pytest.raises(ValueError, match="list"):
        parse_word_list_literal("alpha beta")


# --- boolean (Switch) literal: manufactured_eikonal_ecg.py's
# eikonal_advection_diffusion_approach is a `str | None` parameter, and its
# real test passes "false" through to a value_kind="boolean" entry. ---


@pytest.mark.parametrize("text,expected", [
    ("false", False), ("true", True),
    ("no", False), ("yes", True),
    ("off", False), ("on", True),
    ("FALSE", False), ("True", True),
])
def test_a_real_boolean_literal_parses(text, expected):
    assert parse_boolean_literal(text) is expected


def test_boolean_literal_round_trips_at_the_value_level():
    assert parse_boolean_literal(format_boolean_literal(True)) is True
    assert parse_boolean_literal(format_boolean_literal(False)) is False


def test_a_malformed_boolean_literal_is_refused():
    with pytest.raises(ValueError, match="Switch"):
        parse_boolean_literal("maybe")
