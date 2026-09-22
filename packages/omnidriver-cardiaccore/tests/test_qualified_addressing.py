"""A parameter address identifies one parameter.

Three defects, one cause -- an address that drops information:

* `slot_key` strips the `$SCOPE.` prefix, so `$CARDIAC_SCAR.fiberField` and
  `$CARDIAC_CONDUCTIVITY.fiberField` land in one slot. Which value survives
  depends on catalog iteration order.
* `_template_for` matches `<ventKey>` against any segment, so an undeclared
  binding such as `banana` is accepted as a ventricle.
* `_check_value` accepts any non-empty string for a `vector3` and any `Real`
  for a `scalar`, including `nan` and `inf`.

These are syntactic and finiteness checks. No physiological range is asserted
here; that has a domain owner and is not this module's to decide.
"""

import math

import pytest

from omnidriver.cardiaccore.workflows.overrides import (
    VENT_KEYS,
    declared_path_template,
    qualified_slot_key,
    validate_input_overrides,
)


def test_two_documents_declaring_one_leaf_name_do_not_collide():
    assert qualified_slot_key("$CARDIAC_CONDUCTIVITY.fiberField") != qualified_slot_key(
        "$CARDIAC_SCAR.fiberField"
    )


def test_a_qualified_key_keeps_its_scope_token():
    assert qualified_slot_key("$CARDIAC_CONDUCTIVITY.fiberField") == (
        "$CARDIAC_CONDUCTIVITY.fiberField"
    )


def test_a_nested_leaf_keeps_its_full_path():
    """The reason the unqualified key kept multi-segment paths intact in the
    first place -- a nested leaf must not overwrite a top-level key."""
    assert qualified_slot_key("$CARDIAC_SCAR.channels.channelMultiplier") == (
        "$CARDIAC_SCAR.channels.channelMultiplier"
    )


def test_an_undeclared_dynamic_segment_is_refused():
    assert declared_path_template("$PURKINJE_TREE.banana.seed") is None
    with pytest.raises(ValueError, match="banana"):
        validate_input_overrides({"$PURKINJE_TREE.banana.seed": [1, 2, 3]})


@pytest.mark.parametrize("vent", sorted(VENT_KEYS))
def test_every_declared_ventricle_binding_is_still_accepted(vent):
    path = f"$PURKINJE_TREE.{vent}.seed"
    assert declared_path_template(path) == "$PURKINJE_TREE.<ventKey>.seed"
    assert validate_input_overrides({path: [1.0, 2.0, 3.0]}) == {path: [1.0, 2.0, 3.0]}


def test_a_non_vector_string_is_refused_for_a_vector_entry():
    with pytest.raises(TypeError, match="three numbers"):
        validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": "not a vector at all"})


def test_a_well_formed_vector_string_is_still_accepted():
    value = "(0.1 0.2 0.3)"
    assert validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": value}) == {
        "$PURKINJE_TREE.hisBundleSeed": value
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_scalar_is_refused(value):
    with pytest.raises(ValueError, match="finite"):
        validate_input_overrides({"$CARDIAC_CONDUCTIVITY.df": value})


@pytest.mark.parametrize("bad", [
    [float("nan"), 0.0, 0.0],
    [0.0, float("inf"), 0.0],
    "(1 nan 3)",
])
def test_a_non_finite_vector_component_is_refused(bad):
    with pytest.raises(ValueError, match="finite"):
        validate_input_overrides({"$PURKINJE_TREE.hisBundleSeed": bad})


def test_an_ordinary_finite_scalar_is_still_accepted():
    assert validate_input_overrides({"$CARDIAC_CONDUCTIVITY.df": 0.1}) == {
        "$CARDIAC_CONDUCTIVITY.df": 0.1
    }
