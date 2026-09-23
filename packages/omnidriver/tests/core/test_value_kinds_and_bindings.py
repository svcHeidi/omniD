"""Generic value shapes, closed; physical meaning, elsewhere.

``value_kind`` defaulted to the string "literal" and was validated only by an
adapter's own ``_check_value``, which accepted any non-empty string for a
vector and ``nan`` for a scalar (audit finding S1). Closing the vocabulary in
core gives every adapter one shape check; it does not give core an opinion
about conductivity.

``dynamic_path`` was a bare boolean: a path had placeholders or it did not,
and nothing said which values a placeholder may take. That is why ``banana``
passed as a ventricle at the *resolution* layer (fixed separately in
``omnidriver-cardiaccore``'s ``overrides.py``, audit finding S1). This module
closes the *declaration* side: a catalog entry may name a placeholder's
allowed values, and a partially-declared binding -- naming some placeholders
but silently skipping a sibling -- is refused.

Full closure (every placeholder on every ``dynamic_path`` entry must declare
its domain) is deliberately not enforced here. The catalog surveyed for this
task has 78 ``dynamic_path=True`` declarations and ten distinct placeholder
names; all but the motivating ``<ventKey>`` example are open-ended,
case-author-chosen instance identifiers (``<name>``, ``<electrode>``,
``<region_name>``, ``<constant_name>``, ``<state_name>``, ``<patch>``,
``<scope>``, ``<solver>``, ``<word>``, ``<value>``) with no closed domain to
declare. Forcing one would mean fabricating an enum for something genuinely
open. Leaving ``allowed_bindings`` empty is not "unchecked" in the sense this
task closes -- there is nothing to check for an open identifier -- so it is
accepted; a *partial* declaration on one entry is refused, which is the
specific shape of bug S1 exhibited.
"""

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
    # R2 finding 10: `bytes` is a `collections.abc.Sequence`, so the typed
    # branches that only excluded `str` let `b"abc"` through as three
    # "numbers" (97, 98, 99). The typed-list branch already excluded
    # `(str, bytes)`; vector3 and the dimensioned branches excluded only
    # `str`.
    ("vector3", b"abc", "three"),
    ("dimensioned_scalar", {"value": 1.0, "dimensions": b"1234567"}, "seven"),
    ("dimensioned_tensor", {"value": b"123456789", "dimensions": (0,) * 7}, "sequence"),
])
def test_a_badly_shaped_value_is_reported_with_a_reason(kind, value, reason):
    reasons = dictionary.validate_value_shape(kind, value)
    assert reasons, f"{kind} accepted {value!r}"
    assert any(reason in r for r in reasons), reasons


def test_a_dynamic_path_declares_its_allowed_bindings():
    entry = dictionary.DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.seed", description="",
        value_kind="vector3", dynamic_path=True,
        allowed_bindings={"<ventKey>": ("lv", "rv")},
    )
    assert entry.allowed_bindings["<ventKey>"] == ("lv", "rv")


def test_a_partially_declared_binding_is_refused():
    """Naming some of an entry's placeholders and silently skipping a sibling
    is exactly the shape of audit finding S1: the undeclared placeholder went
    unchecked while its sibling looked covered."""
    with pytest.raises(ValueError, match="<layer>"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.<layer>.x", description="",
            value_kind="scalar", dynamic_path=True,
            allowed_bindings={"<ventKey>": ("lv", "rv")},
        )


def test_an_undeclared_dynamic_path_is_accepted():
    """Most placeholders in this catalog (``<name>``, ``<electrode>``, ...)
    are open-ended, case-author-chosen identifiers with no closed domain.
    Leaving bindings undeclared entirely is honest, not an unchecked hole:
    there is nothing to check for an open identifier."""
    entry = dictionary.DictEntry(
        driver_path="$A.<name>.x", description="",
        value_kind="scalar", dynamic_path=True,
    )
    assert entry.allowed_bindings == {}


def test_declared_bindings_on_a_static_path_are_refused():
    with pytest.raises(ValueError, match="dynamic_path"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="scalar",
            allowed_bindings={"<ventKey>": ("lv",)},
        )


def test_a_binding_key_absent_from_the_path_is_refused():
    with pytest.raises(ValueError, match="<typo>"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.x", description="",
            value_kind="scalar", dynamic_path=True,
            allowed_bindings={"<ventKey>": ("lv", "rv"), "<typo>": ("lv",)},
        )


# --- R2 finding 12: three one-line DictEntry guards, latent on the 258
# production declarations R2 scanned (zero instances today) but cheap to
# close regardless. ---


def test_a_placeholder_without_dynamic_path_is_refused():
    with pytest.raises(ValueError, match="placeholder"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.x", description="", value_kind="scalar",
        )


def test_dynamic_path_with_no_placeholder_is_refused():
    with pytest.raises(ValueError, match="no placeholder"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="scalar",
            dynamic_path=True,
        )


def test_an_empty_binding_domain_is_refused():
    """A placeholder with no allowed value can never be satisfied."""
    with pytest.raises(ValueError, match="empty domain"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.x", description="", value_kind="scalar",
            dynamic_path=True, allowed_bindings={"<ventKey>": ()},
        )


def test_core_asserts_nothing_about_units():
    """``unit`` is the adapter's, supplied where domain evidence justifies it.
    Core carries it and checks nothing against it."""
    entry = dictionary.DictEntry(
        driver_path="$A.x", description="", value_kind="scalar", unit="furlong",
    )
    assert entry.unit == "furlong"
    assert dictionary.validate_value_shape("scalar", 0.1) == ()


def test_no_kind_means_unchecked():
    """Every member of the closed vocabulary has a real shape check; there is
    no member whose validator always returns no reasons regardless of input."""
    for kind in dictionary.VALUE_KINDS:
        reasons = dictionary.validate_value_shape(kind, object())
        assert reasons, f"{kind} accepted an arbitrary object with no reasons"


def test_value_kind_is_mandatory():
    """R2 finding 8: value_kind defaulted first to "literal" (which said
    nothing), then to "word" once that vocabulary closed -- and "word" says
    something specific and can be WRONG. Three production entries
    ($ELECTRO_MODEL_COEFFS.ecgDomains.<name>.sampling.{start,end,deltaT})
    omitted the field and silently declared "word" while actually being
    scalars. A `grep` for `value_kind=` cannot find an entry that omits it;
    a mandatory field cannot be missed the same way."""
    with pytest.raises(TypeError, match="value_kind"):
        dictionary.DictEntry(driver_path="$A.x", description="")
