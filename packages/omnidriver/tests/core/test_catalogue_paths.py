"""Core-owned parsing of plugin ``DictEntry.driver_path`` values."""

from __future__ import annotations

from omnidriver.core.contracts.catalogue_paths import _parse_path


def test_strips_a_scope_token_without_knowing_the_plugin_vocabulary() -> None:
    path = _parse_path("$SOME_PLUGIN_SCOPE.foo.bar", is_dynamic=False)
    assert path.normalised == "foo.bar"
    assert path.leaf == "bar"
    assert path.parents == ("foo",)


def test_leaves_an_unprefixed_path_unchanged() -> None:
    path = _parse_path("mySolver", is_dynamic=False)
    assert path.normalised == "mySolver"


def test_leaves_a_non_token_dollar_prefix_unchanged() -> None:
    path = _parse_path("$notAToken", is_dynamic=False)
    assert path.normalised == "$notAToken"
