"""The composition rules of ``provider_stack.MEMBERS``, as behaviour."""

import pytest

from omnidriver.core import provider_stack


class _Provider:
    """Minimal provider; attributes are set per test."""

    # The profile is built once and memoized, so a test mutating
    # `.get_profile().case_files` in place actually sticks for composition to see.

    def __init__(self, plugin_id, requires=(), case_files=(), **members):
        self.plugin_id = plugin_id
        self._profile = type("_P", (), {})()
        self._profile.requires = tuple(requires)
        self._profile.case_files = tuple(case_files)
        for name, value in members.items():
            setattr(self, name, value)

    def get_profile(self):
        return self._profile


def _compose(*providers):
    return provider_stack.ProviderStack(provider_stack.order_providers(providers))


def test_sets_are_unioned():
    env = _Provider("org.env", get_environment_commands=lambda: frozenset({"blockMesh"}))
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_solver_commands=lambda: frozenset({"theSolver"}),
    )
    composed = _compose(env, solver)
    assert composed.call("get_environment_commands") == frozenset({"blockMesh"})
    assert composed.call("get_solver_commands") == frozenset({"theSolver"})


def test_maps_merge_and_an_unmarked_duplicate_is_an_error():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {"shared": {"from": "solver"}},
    )
    with pytest.raises(ValueError, match="shared"):
        _compose(env, solver).call("get_named_catalogs")


def test_a_marked_override_wins():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {
            "shared": {"from": "solver", "overrides": "org.env"},
        },
    )
    assert _compose(env, solver).call("get_named_catalogs")["shared"]["from"] == "solver"


def test_an_override_naming_a_provider_that_did_not_declare_it_is_an_error():
    """A stale override must surface when what it shadowed is removed."""
    env = _Provider("org.env", get_named_catalogs=lambda: {})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {
            "gone": {"from": "solver", "overrides": "org.env"},
        },
    )
    with pytest.raises(ValueError, match="gone"):
        _compose(env, solver).call("get_named_catalogs")


def test_single_values_take_the_most_specific_non_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: "solver-reader",
    )
    assert _compose(env, solver).call("get_config_value_reader") == "solver-reader"


def test_single_values_fall_through_a_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: None,
    )
    assert _compose(env, solver).call("get_config_value_reader") == "env-reader"


def test_diagnostics_concatenate_in_stack_order():
    env = _Provider("org.env", get_plan_diagnostics=lambda case_root, **kw: ("env-diag",))
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_plan_diagnostics=lambda case_root, **kw: ("solver-diag",),
    )
    composed = _compose(env, solver)
    assert composed.call(
        "get_plan_diagnostics", None, workflow_dag=None, env={}, scratch_root=None, driver_context=None,
    ) == ("env-diag", "solver-diag")


def test_a_stack_with_no_plan_diagnostics_adds_none():
    assert _compose(_Provider("org.only")).call(
        "get_plan_diagnostics", None, workflow_dag=None, env={}, scratch_root=None, driver_context=None,
    ) == ()


def test_resolve_and_supported_modes_must_come_from_one_provider():
    """Which modes a resolver accepts is its own provider's answer."""
    modes_only = _Provider("org.a", get_supported_mutation_modes=lambda: frozenset({"synthesize"}))
    resolver_only = _Provider("org.b", resolve_case_mutation=lambda *a, **k: None)
    assert any("get_supported_mutation_modes" in p for p in provider_stack.check_provider_members(modes_only))
    assert any("get_supported_mutation_modes" in p for p in provider_stack.check_provider_members(resolver_only))
    both = _Provider(
        "org.both",
        resolve_case_mutation=lambda *a, **k: None,
        get_supported_mutation_modes=lambda: frozenset({"clone_and_patch"}),
    )
    assert provider_stack.check_provider_members(both) == []


def test_a_case_file_path_declared_twice_is_an_error():
    """Spec §2.1: one fact, one declarer."""
    rule = type("_R", (), {"path": "system/controlDict", "role": "openfoam.control_dict"})()
    env = _Provider("org.env")
    env.get_profile().case_files = (rule,)
    solver = _Provider("org.solver", requires=("org.env",))
    solver.get_profile().case_files = (rule,)
    with pytest.raises(ValueError, match="system/controlDict"):
        _compose(env, solver)
