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


# --- dynamic bindings are checked against what the entry declares ------------
#
# Audit finding S1 was fixed for `<ventKey>` by teaching `_template_for` the
# `VENT_KEYS` constant. That closed the one instance and left the mechanism
# special-cased: a second placeholder -- `$PURKINJE_SCAR.regions.<region_id>`
# -- was matched by nothing, so a legitimate region override was refused as
# "not declared" while an illegitimate ventricle was caught only because one
# constant happened to be hardcoded in the matcher. These tests pin the
# general mechanism: the domain comes from `DictEntry.allowed_bindings`.

_REGION = "$PURKINJE_SCAR.regions.<region_id>.conductanceReduction"


def test_an_open_dynamic_binding_is_accepted():
    """`regions/3` is what `setPurkinjeScar.C`'s `policyForRegion` reads."""
    path = "$PURKINJE_SCAR.regions.3.conductanceReduction"
    assert declared_path_template(path) == _REGION
    assert validate_input_overrides({path: 0.8}) == {path: 0.8}


def test_an_open_binding_that_is_not_a_word_is_refused():
    path = "$PURKINJE_SCAR.regions.a b.conductanceReduction"
    assert declared_path_template(path) is None
    with pytest.raises(ValueError, match="not a valid word"):
        validate_input_overrides({path: 0.8})


@pytest.mark.parametrize("bad,reason", [
    ("3;evil", "statement separator"),
    ("3#include", "directive"),
])
def test_an_open_binding_carrying_dictionary_syntax_is_refused(bad, reason):
    """The binding becomes a sub-block *name*, and `update_foam_entry`'s own
    security check only ever inspects a written value -- so the refusal must
    come from `check_dictionary_word_is_safe`, by that reason, and not merely
    from the path failing to match any template at all."""
    path = f"$PURKINJE_SCAR.regions.{bad}.conductanceReduction"
    assert declared_path_template(path) is None
    with pytest.raises(ValueError, match=reason):
        validate_input_overrides({path: 0.8})


def test_a_placeholder_with_no_declared_domain_is_refused_not_assumed_open():
    """An *undeclared* placeholder is audit finding S1's hole itself, so it
    is refused rather than silently treated as unconstrained. No production
    entry reaches this branch today (see
    `test_every_dynamic_entry_declares_a_domain_for_every_placeholder`);
    that is the point -- if one ever does, it fails loudly."""
    from omnidriver.core.contracts.dictionary import DictEntry
    from omnidriver.cardiaccore.workflows.overrides import validate_dynamic_binding

    entry = DictEntry(
        driver_path="$PURKINJE_SCAR.regions.<undeclared>.conductanceReduction",
        description="fixture",
        value_kind="scalar",
        dynamic_path=True,
    )
    with pytest.raises(ValueError, match="declares no binding domain"):
        validate_dynamic_binding(entry, "<undeclared>", "3")


def test_reading_a_case_never_reports_a_placeholder_as_a_parameter(tmp_path):
    """`read_input_values` expanded `<ventKey>` from `VENT_KEYS` and left
    every other template unexpanded, so an open-domain path was read
    literally and recorded as `regions.<region_id>...: None` -- a parameter
    address no case has. An open domain has no members to enumerate, so
    there is nothing to read; inventing the placeholder as a key is worse
    than reporting nothing."""
    from omnidriver.cardiaccore.workflows.overrides import read_input_values

    (tmp_path / "system").mkdir()
    values = read_input_values(tmp_path)
    assert [path for path in values if "<" in path] == []
