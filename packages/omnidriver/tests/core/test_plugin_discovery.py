from __future__ import annotations

import dataclasses

import pytest

from omnidriver.core import plugin_discovery
from omnidriver.core.plugin_interface import load_plugin_context
from plugins.minimal_plugin import MinimalTestPlugin


class _FakeEntryPoint:
    name = "fakeplugin"
    value = "plugins.minimal_plugin:MinimalTestPlugin"
    dist = type("D", (), {"name": "fake-dist", "version": "9.9"})()

    def load(self):
        from plugins.minimal_plugin import MinimalTestPlugin

        return MinimalTestPlugin


def test_a_colon_still_means_a_trusted_local_import() -> None:
    context = load_plugin_context(
        "plugins.minimal_plugin:MinimalTestPlugin"
    )
    # StackIdentity has no singular id/source -- one per provider, on
    # StackIdentity.providers (a tuple of ProviderIdentity). A single-plugin
    # driver_context composes to a one-entry stack.
    assert context.identity.providers[0].id == "org.driverfoam.test-minimal"
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
        "plugins.minimal_plugin:MinimalTestPlugin"
    )
    assert context.identity.providers[0].source.startswith("trusted-import:")


def test_discovery_is_empty_by_default_and_does_not_raise() -> None:
    # No third-party plugin is installed in this repository's environment.
    assert isinstance(plugin_discovery.discover_plugins(), dict)


def test_no_installed_adapter_never_creates_an_environment_fallback(monkeypatch) -> None:
    monkeypatch.setattr(plugin_discovery, "_entry_points", lambda: ())
    plugin_discovery._default_selection.cache_clear()

    with pytest.raises(LookupError, match="no adapter is installed"):
        plugin_discovery.default_discovered_context()


class _RivalEntryPoint(_FakeEntryPoint):
    """A second distribution claiming the same entry-point name."""

    dist = type("D", (), {"name": "rival-dist", "version": "0.1"})()


def test_a_name_claimed_by_two_distributions_is_reported_not_resolved(
    monkeypatch,
) -> None:
    """Insertion order must not silently decide which plugin wins -- that
    would depend on installation order and be invisible in the plan."""
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


# -- Solver-tier root detection (Task 9's second correction) ------------------
#
# `_default_selection` used to compose every unambiguous adapter together
# unconditionally. These fakes are `MinimalTestPlugin` with a chosen
# `plugin_id` and `requires:`, so the graph these tests exercise (one shared
# "environment" id, one or two "solver" ids that only require it) does not
# depend on any real adapter package being installed.


class _NamedTestPlugin(MinimalTestPlugin):
    """A `MinimalTestPlugin` whose id and `requires:` are chosen per instance."""

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
    """An entry point whose ``load()`` returns ``plugin_class`` unchanged.

    ``plugin_class`` must be constructible with no arguments -- every caller
    in `plugin_discovery.py` instantiates a loaded class as ``cls()``, the
    same as a real ``[project.entry-points...]`` target.
    """
    dist = type("D", (), {"name": f"{name}-dist", "version": "1.0"})()
    return type(
        "_FakeEntryPoint", (), {"name": name, "dist": dist, "load": lambda self: plugin_class},
    )()


_ENV_ID = "test.environment"


def _env_entry_point(name: str = "test-environment"):
    return _fake_entry_point(name, lambda: _NamedTestPlugin(_ENV_ID))


def _solver_entry_point(name: str):
    return _fake_entry_point(name, lambda: _NamedTestPlugin(name, requires=(_ENV_ID,)))


def test_one_solver_tier_root_still_composes_with_no_plugin_flag(monkeypatch) -> None:
    """The common case Task 7 stopped refusing must keep working: exactly one
    solver-tier adapter, plus the environment provider it requires, composes
    with no --plugin needed."""
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (_env_entry_point(), _solver_entry_point("test.solver")),
    )
    plugin_discovery._default_selection.cache_clear()

    context = plugin_discovery.default_discovered_context()

    ids = {p.id for p in context.identity.providers}
    assert ids == {_ENV_ID, "test.solver"}


def test_two_independent_solver_tier_plugins_are_refused_by_name(monkeypatch) -> None:
    """Two adapters with no requires: relationship between them -- each only
    requiring the shared environment provider, neither requiring the other --
    must not be silently composed together; that is exactly the ambiguity
    that produced a wrong single-shape resolution (Task 9)."""
    monkeypatch.setattr(
        plugin_discovery,
        "_entry_points",
        lambda: (
            _env_entry_point(),
            _solver_entry_point("test.solver-a"),
            _solver_entry_point("test.solver-b"),
        ),
    )
    plugin_discovery._default_selection.cache_clear()

    with pytest.raises(LookupError, match="test.solver-a") as excinfo:
        plugin_discovery.default_discovered_context()
    assert "test.solver-b" in str(excinfo.value)
    assert "--plugin" in str(excinfo.value)
