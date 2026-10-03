from __future__ import annotations

import dataclasses
from importlib.metadata import EntryPoint

import pytest

from omnidriver.core import plugin_discovery
from omnidriver.core.plugin_interface import load_plugin_context
from plugins.toy import ToyProvider


class _FakeEntryPoint:
    name = "fakeplugin"
    value = "plugins.toy:ToyProvider"
    dist = type("D", (), {"name": "fake-dist", "version": "9.9"})()

    def load(self):
        from plugins.toy import ToyProvider

        return ToyProvider


def test_a_colon_still_means_a_trusted_local_import() -> None:
    context = load_plugin_context(
        "plugins.toy:ToyProvider"
    )
    # StackIdentity has no singular id/source -- one per provider, on
    # StackIdentity.providers (a tuple of ProviderIdentity). A single-plugin
    # driver_context composes to a one-entry stack.
    assert context.identity.providers[0].id == "org.omnidriver.test-minimal"
    assert context.identity.providers[0].source.startswith("trusted-import:")


def test_an_unknown_discovered_id_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="definitelyNotInstalled"):
        load_plugin_context("definitelyNotInstalled")


def test_discovery_reads_the_omnidriver_plugins_group(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_discovery, "_entry_points", lambda: (_FakeEntryPoint(),)
    )
    assert "fakeplugin" in plugin_discovery.discover_plugins()
    context = plugin_discovery.load_discovered_plugin("fakeplugin")
    # Identity provenance records the installing distribution, so a plan says
    # which package supplied the semantics it was built against. One
    # ProviderIdentity per provider on StackIdentity.providers; this is a
    # one-provider stack.
    assert context.identity.providers[0].source == "entry-point:fake-dist=9.9"


def test_a_discovered_id_wins_only_when_there_is_no_colon(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_discovery, "_entry_points", lambda: (_FakeEntryPoint(),)
    )
    # A colon always means the trusted import form, never discovery.
    context = load_plugin_context(
        "plugins.toy:ToyProvider"
    )
    assert context.identity.providers[0].source.startswith("trusted-import:")


def test_a_loaded_context_records_the_selector_that_rebuilds_it(monkeypatch) -> None:
    """A child process can only rebuild a context from the selector string."""
    monkeypatch.setattr(
        plugin_discovery, "_entry_points", lambda: (_FakeEntryPoint(),)
    )
    target = "plugins.toy:ToyProvider"
    assert load_plugin_context(target).plugin_selector == target
    assert load_plugin_context("fakeplugin").plugin_selector == "fakeplugin"


def test_a_hand_built_context_claims_no_selector() -> None:
    """No selector string produced it, so it must not pretend one would."""
    from omnidriver.core.plugin_interface import driver_context

    context = driver_context(ToyProvider(), source="test:hand-built")
    assert context.plugin_selector is None


def test_the_selector_is_not_part_of_context_equality() -> None:
    """It says how to rebuild a context, not what the context is."""
    context = load_plugin_context("plugins.toy:ToyProvider")
    rebuilt = dataclasses.replace(context, plugin_selector=None)
    assert rebuilt == context


def test_discovery_is_empty_by_default_and_does_not_raise() -> None:
    # No third-party plugin is installed in this repository's environment.
    assert isinstance(plugin_discovery.discover_plugins(), dict)


class _RivalEntryPoint(_FakeEntryPoint):
    """A second distribution claiming the same entry-point name."""

    dist = type("D", (), {"name": "rival-dist", "version": "0.1"})()


def test_a_name_claimed_by_two_distributions_is_reported_not_resolved(
    monkeypatch,
) -> None:
    """Insertion order must not silently decide which plugin wins -- that would depend on installation order and be invisible in the plan."""
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_FakeEntryPoint(), _RivalEntryPoint()),
    )
    ambiguous = plugin_discovery.ambiguous_plugin_names()
    assert ambiguous == {"fakeplugin": ("fake-dist=9.9", "rival-dist=0.1")}
    # The ambiguous name is withheld from discovery rather than resolved.
    assert "fakeplugin" not in plugin_discovery.discover_plugins()


def test_loading_an_ambiguous_name_fails_loudly(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_FakeEntryPoint(), _RivalEntryPoint()),
    )
    with pytest.raises(KeyError, match="claimed by more than one"):
        plugin_discovery.load_discovered_plugin("fakeplugin")


# -- Solver-tier root detection -----------------------------------------------
#
# These fakes are `ToyProvider` with a chosen `plugin_id` and
# `requires:`, so the graph these tests exercise (one shared "environment"
# id, one or two "solver" ids that only require it) does not depend on any
# real adapter package being installed.


class _NamedTestPlugin(ToyProvider):
    """A `ToyProvider` whose id and `requires:` are chosen per instance."""

    def __init__(self, plugin_id: str, requires: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._named_plugin_id = plugin_id
        self._named_requires = requires

    @property
    def plugin_id(self) -> str:
        return self._named_plugin_id

    def get_profile(self):
        return dataclasses.replace(super().get_profile(), requires=self._named_requires)


def _fake_entry_point(name: str, plugin_class: type):
    """An entry point whose ``load()`` returns ``plugin_class`` unchanged."""
    dist = type("D", (), {"name": f"{name}-dist", "version": "1.0"})()
    return type(
        "_FakeEntryPoint", (), {"name": name, "dist": dist, "load": lambda self: plugin_class},
    )()


_ENV_ID = "test.environment"


def _env_entry_point(name: str = "test-environment"):
    return _fake_entry_point(name, lambda: _NamedTestPlugin(_ENV_ID))


def _solver_entry_point(name: str):
    return _fake_entry_point(name, lambda: _NamedTestPlugin(name, requires=(_ENV_ID,)))


def test_a_named_plugin_composes_with_the_environment_provider_it_requires(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_env_entry_point(), _solver_entry_point("test.solver")),
    )

    context = plugin_discovery.load_discovered_plugin("test.solver")

    assert {p.id for p in context.identity.providers} == {_ENV_ID, "test.solver"}


# -- A broken entry point is refused by name --------------------------------
#
# A real ``importlib.metadata.EntryPoint`` whose target module does not exist,
# so ``load()`` raises the genuine ``ModuleNotFoundError`` a half-installed
# third-party distribution would. One such entry anywhere in the group must
# not abort an explicit ``--plugin`` for an unrelated, working stack.

_BROKEN_TARGET = "no_such_module_omnidriver_test.plugin:Plugin"


def _broken_entry_point(name: str = "aaa-broken"):
    return EntryPoint(name, _BROKEN_TARGET, plugin_discovery.ENTRY_POINT_GROUP)


def test_a_working_named_plugin_loads_beside_a_broken_sibling(monkeypatch) -> None:
    """The broken entry sorts first, so an order-dependent scan would hit it before the provider the named plugin's ``requires:`` actually needs."""
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_broken_entry_point(), _env_entry_point(), _solver_entry_point("test.solver")),
    )

    context = plugin_discovery.load_discovered_plugin("test.solver")

    assert {p.id for p in context.identity.providers} == {_ENV_ID, "test.solver"}


def test_loading_the_broken_plugin_refuses_by_name(monkeypatch) -> None:
    monkeypatch.setattr(
        plugin_discovery, "_entry_points", lambda: (_broken_entry_point(), _env_entry_point()),
    )
    with pytest.raises(LookupError, match="aaa-broken") as excinfo:
        plugin_discovery.load_discovered_plugin("aaa-broken")
    message = str(excinfo.value)
    assert _BROKEN_TARGET in message
    assert "No module named 'no_such_module_omnidriver_test'" in message


def test_an_unmet_requirement_names_broken_entries_as_possible_providers(monkeypatch) -> None:
    """Nothing loadable answers the required id; the broken entry might have, so the refusal names it rather than letting ``order_providers`` report a plain 'missing' that hides the likely cause."""
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_broken_entry_point(), _solver_entry_point("test.solver")),
    )
    with pytest.raises(LookupError, match=_ENV_ID) as excinfo:
        plugin_discovery.load_discovered_plugin("test.solver")
    assert "aaa-broken" in str(excinfo.value)
    assert _BROKEN_TARGET in str(excinfo.value)
