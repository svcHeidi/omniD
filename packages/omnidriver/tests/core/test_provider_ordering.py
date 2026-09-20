"""A provider declares what it provides and what it layers on."""

import pytest
import yaml

from omnidriver.core import plugin_profile


def _profile(tmp_path, payload):
    path = tmp_path / "plugin.yaml"
    path.write_text(yaml.safe_dump(payload))
    return plugin_profile.load_plugin_profile(path)


BASE = {
    "schema_version": 1,
    "plugin": {"id": "org.example.thing", "api_version": "2"},
    "case_profile": {"dictionaries": []},
}


def test_provides_and_requires_default_to_empty(tmp_path):
    profile = _profile(tmp_path, dict(BASE))
    assert profile.provides == frozenset()
    assert profile.requires == ()


def test_provides_is_read(tmp_path):
    payload = dict(BASE, provides=["command_authorization", "case_files"])
    profile = _profile(tmp_path, payload)
    assert profile.provides == frozenset({"command_authorization", "case_files"})


def test_requires_preserves_order(tmp_path):
    payload = dict(BASE, requires=["org.omnidriver.openfoam", "org.example.mid"])
    profile = _profile(tmp_path, payload)
    assert profile.requires == ("org.omnidriver.openfoam", "org.example.mid")


def test_provides_rejects_an_unknown_capability(tmp_path):
    payload = dict(BASE, provides=["not_a_capability"])
    with pytest.raises(ValueError, match="not_a_capability"):
        _profile(tmp_path, payload)


def test_declared_provides_must_match_implementation():
    """A misspelled hook name must be an error, not a silent fallback."""
    from omnidriver.core import provider_stack

    class _Claims:
        """Declares command_authorization but misspells one of its members."""
        def get_solver_commands(self): return frozenset()
        def get_auxiliary_commands(self): return frozenset()
        def get_utility_manifest(self): return {}          # typo: no trailing s
        def get_utility_roots(self): return ()

        class _Profile:
            provides = frozenset({"command_authorization"})
        def get_profile(self): return self._Profile()

    problems = provider_stack.check_provides(_Claims())
    assert problems, "a misspelled member must be reported"
    assert any("get_utility_manifests" in p for p in problems)


def test_matching_declaration_reports_nothing():
    from omnidriver.core import provider_stack

    class _Honest:
        def get_solver_commands(self): return frozenset()
        def get_auxiliary_commands(self): return frozenset()
        def get_utility_manifests(self): return {}
        def get_utility_roots(self): return ()
        def get_environment_commands(self): return frozenset()
        def is_installed_environment_command(self, command): return False

        class _Profile:
            provides = frozenset({"command_authorization"})
        def get_profile(self): return self._Profile()

    assert provider_stack.check_provides(_Honest()) == []


def _fake(plugin_id, requires=(), provides=frozenset()):
    class _P:
        class _Profile:
            pass
        def get_profile(self):
            profile = self._Profile()
            profile.requires = requires
            profile.provides = provides
            return profile
    p = _P()
    p.plugin_id = plugin_id
    return p


def test_ordering_puts_requirements_first():
    from omnidriver.core import provider_stack

    env = _fake("org.env")
    solver = _fake("org.solver", requires=("org.env",))
    ordered = provider_stack.order_providers([solver, env])
    assert [p.plugin_id for p in ordered] == ["org.env", "org.solver"]


def test_ordering_is_stable_for_independent_providers():
    from omnidriver.core import provider_stack

    a, b = _fake("org.a"), _fake("org.b")
    assert [p.plugin_id for p in provider_stack.order_providers([a, b])] == [
        "org.a", "org.b",
    ]
    assert [p.plugin_id for p in provider_stack.order_providers([b, a])] == [
        "org.a", "org.b",
    ]


def test_a_cycle_is_refused_by_name():
    from omnidriver.core import provider_stack

    a = _fake("org.a", requires=("org.b",))
    b = _fake("org.b", requires=("org.a",))
    with pytest.raises(ValueError, match="org.a"):
        provider_stack.order_providers([a, b])


def test_a_missing_requirement_is_refused_by_name():
    from omnidriver.core import provider_stack

    solver = _fake("org.solver", requires=("org.absent",))
    with pytest.raises(ValueError, match="org.absent"):
        provider_stack.order_providers([solver])
