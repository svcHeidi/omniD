"""A provider declares what it layers on; the stack orders and composes it."""

import pytest
import yaml

from omnidriver.core import plugin_profile


def _profile(tmp_path, payload):
    path = tmp_path / "plugin.yaml"
    path.write_text(yaml.safe_dump(payload))
    return plugin_profile.load_plugin_profile(path)


BASE = {
    "schema_version": 1,
    "plugin": {"id": "org.example.thing", "api_version": "3"},
    "case_profile": {"dictionaries": []},
}


def test_requires_defaults_to_empty(tmp_path):
    assert _profile(tmp_path, dict(BASE)).requires == ()


def test_requires_preserves_order(tmp_path):
    payload = dict(BASE, requires=["org.omnidriver.openfoam", "org.example.mid"])
    profile = _profile(tmp_path, payload)
    assert profile.requires == ("org.omnidriver.openfoam", "org.example.mid")


def _fake(plugin_id, requires=()):
    class _P:
        class _Profile:
            pass
        def get_profile(self):
            profile = self._Profile()
            profile.requires = requires
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


def _fake_with_profile(plugin_id, *, requires=(), case_files=(), **members):
    """A provider whose ``get_profile()`` returns the same object every call, so mutating it after construction is observed."""
    class _Profile:
        pass

    profile = _Profile()
    profile.requires = tuple(requires)
    profile.case_files = tuple(case_files)
    profile.digest = f"sha256:{plugin_id}"

    class _P:
        def get_profile(self):
            return profile

    provider = _P()
    provider.plugin_id = plugin_id
    for name, value in members.items():
        setattr(provider, name, value)
    return provider


def _rule(path, required="always"):
    return type("_R", (), {
        "path": path, "role": "openfoam.control_dict",
        "kind": "dictionary", "required": required,
    })()


def test_a_case_file_path_declared_by_two_providers_is_an_error():
    """Spec §2.1: one fact, one declarer -- across the stack, not per provider."""
    from omnidriver.core import provider_stack

    rule = _rule("system/controlDict")
    env = _fake_with_profile("org.env", case_files=(rule,))
    solver = _fake_with_profile(
        "org.solver", requires=("org.env",), case_files=(rule,),
    )
    with pytest.raises(ValueError, match="system/controlDict"):
        provider_stack.ProviderStack(provider_stack.order_providers([env, solver]))


def test_distinct_case_file_paths_compose():
    from omnidriver.core import provider_stack

    env = _fake_with_profile("org.env", case_files=(_rule("system/controlDict"),))
    solver = _fake_with_profile(
        "org.solver", requires=("org.env",),
        case_files=(_rule("constant/electroProperties"),),
    )
    composed = provider_stack.ProviderStack(provider_stack.order_providers([env, solver]))
    assert sorted(rule.path for rule in composed.call("get_profile").case_files) == [
        "constant/electroProperties", "system/controlDict",
    ]


def test_resolutions_name_a_winner_for_every_member():
    from omnidriver.core import provider_stack

    env = _fake_with_profile(
        "org.env", get_environment_commands=lambda: frozenset({"blockMesh"}),
    )
    solver = _fake_with_profile(
        "org.solver", requires=("org.env",),
        get_solver_commands=lambda: frozenset({"theSolver"}),
    )
    resolved = provider_stack.resolutions(
        provider_stack.ProviderStack(provider_stack.order_providers([env, solver]))
    )
    assert set(resolved) == set(provider_stack.MEMBERS)
    assert resolved["get_environment_commands"][0] == "org.env"
    assert resolved["get_solver_commands"][0] == "org.solver"
    assert resolved["get_named_catalogs"] == (provider_stack.UNCLAIMED, provider_stack.RESOLUTION_PLACEHOLDER)
    # Only the profile, dictionary entries and manifest carry a content
    # digest; the rest record the winner alone.
    assert resolved["get_solver_commands"][1] == provider_stack.RESOLUTION_PLACEHOLDER
    assert resolved["get_profile"][1].startswith("sha256:")
