"""``OpenFOAMEnvironmentPlugin.get_case_value_comparator`` -- the typed
``CaseValueComparisonCapability`` answer (step 4a of
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §5).

Every case here is one design step 4a itself names: "0.000560538" agrees
with "0.000560538", "yes" with True, "(1 2 3)" with [1, 2, 3], and 1 does
NOT agree with True -- proving the comparator is typed, not string/``==``
equality.
"""

from __future__ import annotations

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def _comparator():
    return OpenFOAMEnvironmentPlugin().get_case_value_comparator()


def test_matching_scalar_text_agrees():
    agree = _comparator()
    assert agree("scalar", 0.000560538, "0.000560538") is True


def test_a_python_float_agrees_with_its_own_native_text_spelling():
    agree = _comparator()
    assert agree("scalar", 1e-3, "0.001") is True


def test_boolean_word_agrees_with_python_true():
    agree = _comparator()
    assert agree("boolean", True, "yes") is True
    assert agree("boolean", False, "no") is True


def test_vector_text_agrees_with_a_python_list():
    agree = _comparator()
    assert agree("vector3", [1, 2, 3], "(1 2 3)") is True


def test_an_integer_does_not_agree_with_a_boolean_word():
    """1 must NOT agree with True -- an int and a bool are different kinds
    even though Python's own `1 == True` says otherwise."""
    agree = _comparator()
    assert agree("integer", 1, "true") is False


def test_a_mismatched_scalar_disagrees():
    agree = _comparator()
    assert agree("scalar", 0.4, "0.5") is False


def test_a_missing_current_value_never_agrees():
    agree = _comparator()
    assert agree("scalar", 0.4, None) is False


def test_value_kind_is_accepted_but_never_drives_the_comparison():
    """The composed stack is single-shape (only one provider's comparator
    ever answers) -- this one must be correct for every value_kind a study
    names, cardiac or OpenFOAM-owned, so it does not attempt to dispatch on
    value_kind at all."""
    agree = _comparator()
    assert agree("word", "80 80 80", "80 80 80") is True
    assert agree("hex_cell_counts", "80 80 70", "80 80 30") is False
