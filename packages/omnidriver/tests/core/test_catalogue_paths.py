"""``slot_key``'s scope-token stripping: a syntactic transform that must not
hardcode the cardiac plugin's token, since another plugin can register its own
under the same `$TOKEN.` convention."""
from __future__ import annotations

from omnidriver.core.contracts.catalogue_paths import catalogued_paths, slot_key
from omnidriver.core.contracts.dictionary import DictEntry


def test_strips_the_cardiac_scope_token() -> None:
    assert slot_key("$ELECTRO_MODEL_COEFFS.myocardiumSolver") == "myocardiumSolver"


def test_strips_an_arbitrary_scope_token_of_the_same_shape() -> None:
    assert slot_key("$SOME_OTHER_PLUGIN_COEFFS.foo.bar") == "foo.bar"


def test_leaves_an_unprefixed_path_unchanged() -> None:
    assert slot_key("myocardiumSolver") == "myocardiumSolver"


def test_leaves_a_dollar_sign_not_matching_the_scope_token_shape_unchanged() -> None:
    assert slot_key("$notAToken") == "$notAToken"


def test_a_catalogue_is_its_entries_paths_without_their_scope_token() -> None:
    entries = [DictEntry(driver_path=path, description="", value_kind="word") for path in ("$S.a.<name>.b", "c")]
    assert catalogued_paths(entries) == ("a.<name>.b", "c")
