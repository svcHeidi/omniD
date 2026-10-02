"""Generic value shapes, closed; physical meaning, elsewhere."""

import pytest

from omnidriver.core.contracts import dictionary


def test_the_vocabulary_is_closed():
    with pytest.raises(ValueError, match="literal"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="literal",
        )


@pytest.mark.parametrize("kind", sorted(dictionary.VALUE_KINDS))
def test_every_declared_kind_is_accepted(kind):
    assert dictionary.DictEntry(
        driver_path="$A.x", description="", value_kind=kind,
    ).value_kind == kind


@pytest.mark.parametrize("kind,value", [
    ("scalar", 0.1),
    ("integer", 3),
    ("boolean", True),
    ("word", "TT06"),
    ("enum", "TT06"),
    ("vector3", (1.0, 2.0, 3.0)),
    ("dimensioned_scalar", {"value": 1.0, "dimensions": (0, 2, -1, 0, 0, 0, 0)}),
    ("dimensioned_tensor", {
        "value": (0.1334, 0, 0, 0.01761, 0, 0.01761),
        "dimensions": (-1, -3, 3, 0, 0, 2, 0),
    }),
    ("word_list", ("alpha", "beta")),
    ("scalar_list", (1.0, 2.0, 3.0)),
    ("vector3_list", ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
    ("integer_list", (0, 1, 2)),
    ("mapping", {"s1_interval_ms": 2000, "n_s1": 10}),
])
def test_a_well_shaped_value_passes(kind, value):
    assert dictionary.validate_value_shape(kind, value) == ()


@pytest.mark.parametrize("kind,value,reason", [
    ("scalar", float("nan"), "finite"),
    ("scalar", float("inf"), "finite"),
    ("scalar", "0.1", "number"),
    ("integer", 1.5, "integer"),
    ("integer", True, "integer"),
    ("boolean", 1, "boolean"),
    ("word", "", "empty"),
    ("word", "two words", "whitespace"),
    ("vector3", (1.0, 2.0), "three"),
    ("vector3", (1.0, 2.0, float("nan")), "finite"),
    ("vector3", "not a vector", "three"),
    ("dimensioned_scalar", {"value": 1.0}, "dimensions"),
    ("dimensioned_scalar", {"value": 1.0, "dimensions": (0, 2)}, "seven"),
    ("dimensioned_scalar", {"value": float("nan"), "dimensions": (0,) * 7}, "finite"),
    ("dimensioned_tensor", {"value": 1.0, "dimensions": (0,) * 7}, "sequence"),
    ("dimensioned_tensor", {"dimensions": (0,) * 7}, "value"),
    ("word_list", 1.0, "sequence"),
    ("word_list", ("alpha", ""), "empty"),
    ("scalar_list", ("1", "2"), "number"),
    ("integer_list", (1.5,), "integer"),
    # `bytes` is a `collections.abc.Sequence`, so a branch that excludes only
    # `str` (not `(str, bytes)`) would let `b"abc"` through as three "numbers".
    ("vector3", b"abc", "three"),
    ("dimensioned_scalar", {"value": 1.0, "dimensions": b"1234567"}, "seven"),
    ("dimensioned_tensor", {"value": b"123456789", "dimensions": (0,) * 7}, "sequence"),
    ("mapping", "not a mapping", "mapping"),
    ("mapping", (1, 2, 3), "mapping"),
])
def test_a_badly_shaped_value_is_reported_with_a_reason(kind, value, reason):
    reasons = dictionary.validate_value_shape(kind, value)
    assert reasons, f"{kind} accepted {value!r}"
    assert any(reason in r for r in reasons), reasons


def test_a_dynamic_path_declares_its_allowed_bindings():
    entry = dictionary.DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.seed", description="",
        value_kind="vector3", 
        allowed_bindings={"<ventKey>": ("lv", "rv")},
    )
    assert entry.allowed_bindings["<ventKey>"] == ("lv", "rv")


def test_a_partially_declared_binding_is_refused():
    """Naming some of an entry's placeholders and silently skipping a sibling would leave the undeclared one unchecked while its sibling looks covered."""
    with pytest.raises(ValueError, match="<layer>"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.<layer>.x", description="",
            value_kind="scalar", 
            allowed_bindings={"<ventKey>": ("lv", "rv")},
        )


def test_an_undeclared_dynamic_path_is_accepted():
    """Leaving bindings undeclared is honest, not an unchecked hole: there is nothing to check for an open, case-author-chosen identifier."""
    entry = dictionary.DictEntry(
        driver_path="$A.<name>.x", description="",
        value_kind="scalar", 
    )
    assert entry.allowed_bindings == {}


def test_an_explicitly_open_domain_is_declared_not_absent():
    """`None` is a legal, stated domain, distinct from the placeholder being absent from `allowed_bindings` altogether."""
    entry = dictionary.DictEntry(
        driver_path="$A.<name>.x", description="",
        value_kind="scalar", 
        allowed_bindings={"<name>": None},
    )
    assert entry.allowed_bindings == {"<name>": None}
    assert "<name>" in entry.allowed_bindings  # declared, not merely defaulted


def test_an_open_domain_does_not_trip_the_empty_domain_refusal():
    """`None` (open, declared) must not be confused with `()` (closed and impossible to satisfy)."""
    entry = dictionary.DictEntry(
        driver_path="$A.<ventKey>.<name>.x", description="",
        value_kind="scalar", 
        allowed_bindings={"<ventKey>": ("lv", "rv"), "<name>": None},
    )
    assert entry.allowed_bindings["<ventKey>"] == ("lv", "rv")
    assert entry.allowed_bindings["<name>"] is None


def test_a_closed_empty_domain_is_still_refused_even_alongside_an_open_one():
    with pytest.raises(ValueError, match="empty domain"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.<name>.x", description="",
            value_kind="scalar", 
            allowed_bindings={"<ventKey>": (), "<name>": None},
        )


def test_declared_bindings_on_a_static_path_are_refused():
    with pytest.raises(ValueError, match="no placeholder"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="scalar",
            allowed_bindings={"<ventKey>": ("lv",)},
        )


def test_a_binding_key_absent_from_the_path_is_refused():
    with pytest.raises(ValueError, match="<typo>"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.x", description="",
            value_kind="scalar", 
            allowed_bindings={"<ventKey>": ("lv", "rv"), "<typo>": ("lv",)},
        )


# --- A path with a placeholder is a dynamic path; nothing declares it. ---


def test_a_path_is_dynamic_exactly_when_it_holds_a_placeholder():
    assert dictionary.DictEntry(driver_path="$A.<ventKey>.x", description="", value_kind="scalar").dynamic_path
    assert not dictionary.DictEntry(driver_path="$A.x", description="", value_kind="scalar").dynamic_path


def test_an_empty_binding_domain_is_refused():
    """A placeholder with no allowed value can never be satisfied."""
    with pytest.raises(ValueError, match="empty domain"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.x", description="", value_kind="scalar",
            allowed_bindings={"<ventKey>": ()},
        )


def test_core_asserts_nothing_about_units():
    """``unit`` is the adapter's, supplied where domain evidence justifies it."""
    entry = dictionary.DictEntry(
        driver_path="$A.x", description="", value_kind="scalar", unit="furlong",
    )
    assert entry.unit == "furlong"
    assert dictionary.validate_value_shape("scalar", 0.1) == ()


def test_no_kind_means_unchecked():
    """Every member of the closed vocabulary has a real shape check; there is no member whose validator always returns no reasons regardless of input."""
    for kind in dictionary.VALUE_KINDS:
        reasons = dictionary.validate_value_shape(kind, object())
        assert reasons, f"{kind} accepted an arbitrary object with no reasons"


def test_value_kind_is_mandatory():
    """A default of "word" would say something specific and could be wrong; "literal" said nothing, but a default is worse than mandatory."""
    with pytest.raises(TypeError, match="value_kind"):
        dictionary.DictEntry(driver_path="$A.x", description="")


def test_string_value_kind_K6():
    """openCARP's String/RFile/WFile parameters may be empty or contain spaces; `word` refuses both."""
    assert "string" in dictionary.VALUE_KINDS
    assert dictionary.validate_value_shape("string", "") == ()
    assert dictionary.validate_value_shape("string", "two words") == ()
    assert dictionary.validate_value_shape("string", 3) == ("must be a string",)
