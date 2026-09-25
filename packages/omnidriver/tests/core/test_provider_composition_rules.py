"""The six composition rules from spec §4.3, as behaviour.

Deliberately mechanism-independent: whichever dispatch mechanism Phase 0's
spike selected, these must pass unchanged.
"""

import pytest

from omnidriver.core import provider_stack


class _Provider:
    """Minimal provider; attributes are set per test.

    The profile is built ONCE and memoized. Corrected 2026-09-21: it used to be
    rebuilt per call, so a test that did `p.get_profile().case_files = (rule,)`
    set the attribute on a throwaway object and composition could never see it.
    That made `test_a_case_file_path_declared_twice_is_an_error` unsatisfiable
    by any implementation -- a fixture defect masquerading as a failing rule.
    """

    def __init__(self, plugin_id, provides=frozenset(), requires=(),
                 case_files=(), **members):
        self.plugin_id = plugin_id
        self._profile = type("_P", (), {})()
        self._profile.provides = frozenset(provides)
        self._profile.requires = tuple(requires)
        self._profile.case_files = tuple(case_files)
        for name, value in members.items():
            setattr(self, name, value)

    def get_profile(self):
        return self._profile


def _compose(*providers):
    return provider_stack.compose(provider_stack.order_providers(providers))


def test_sets_are_unioned():
    env = _Provider("org.env", get_environment_commands=lambda: frozenset({"blockMesh"}))
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_solver_commands=lambda: frozenset({"theSolver"}),
    )
    composed = _compose(env, solver)
    assert composed.command_authorization.environment_commands() == frozenset({"blockMesh"})
    assert composed.command_authorization.solver_commands() == frozenset({"theSolver"})


def test_maps_merge_and_an_unmarked_duplicate_is_an_error():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {"shared": {"from": "solver"}},
    )
    with pytest.raises(ValueError, match="shared"):
        _compose(env, solver).named_catalogs.catalogs()


def test_a_marked_override_wins():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {
            "shared": {"from": "solver", "overrides": "org.env"},
        },
    )
    assert _compose(env, solver).named_catalogs.catalogs()["shared"]["from"] == "solver"


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
        _compose(env, solver).named_catalogs.catalogs()


def test_a_duplicate_axis_name_across_two_providers_is_refused():
    """``get_axis_catalog`` is ``map``-shaped (``provider_stack._SHAPE``), the
    same generic merge ``test_maps_merge_and_an_unmarked_duplicate_is_an_
    error`` already proves for ``get_named_catalogs`` -- this pins the SAME
    mechanism for a real ``AxisContract`` value, not a plain dict.

    ``_override_marker`` reads ``value.get("overrides")`` and treats an
    ``AttributeError`` (no such method) as "no marker" -- an ``AxisContract``
    is a frozen dataclass with no ``.get`` at all, so it can NEVER carry an
    override marker the way a plain-dict catalog entry can. Two providers
    declaring the same axis name are therefore an UNMARKED duplicate every
    time, with no override escape hatch -- confirmed here rather than left
    to the generic dict-shaped test's coincidental coverage, per the step-3
    instruction to confirm (or fix) this by name.
    """
    from omnidriver.core.tutorial_records import AxisContract, AxisResult

    def _resolve(value, staged_case_root):
        return AxisResult()

    axis_a = AxisContract(name="number_cells", value_kind="integer", resolve=_resolve)
    axis_b = AxisContract(name="number_cells", value_kind="integer", resolve=_resolve)
    env = _Provider("org.env", get_axis_catalog=lambda: {"number_cells": axis_a})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_axis_catalog=lambda: {"number_cells": axis_b},
    )
    with pytest.raises(ValueError, match="number_cells"):
        _compose(env, solver).axes.catalog()


def test_single_values_take_the_most_specific_non_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: "solver-reader",
    )
    assert _compose(env, solver).config_value.reader() == "solver-reader"


def test_single_values_fall_through_a_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: None,
    )
    assert _compose(env, solver).config_value.reader() == "env-reader"


def test_diagnostics_concatenate_in_stack_order():
    env = _Provider(
        "org.env",
        get_base_mesh_geometry_diagnostics=lambda case_root: ("env-diag",),
    )
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_base_mesh_geometry_diagnostics=lambda case_root: ("solver-diag",),
    )
    composed = _compose(env, solver)
    assert composed.mesh_diagnostic_policy.base_geometry_diagnostics(None) == (
        "env-diag", "solver-diag",
    )


def test_two_providers_implementing_a_refusing_hook_is_an_error():
    a = _Provider("org.a", materialize_sweep_case=lambda **kw: None,
                  route_sweep_case_values=lambda **kw: {})
    b = _Provider("org.b", requires=("org.a",),
                  materialize_sweep_case=lambda **kw: None,
                  route_sweep_case_values=lambda **kw: {})
    with pytest.raises(ValueError, match="materialize_sweep_case"):
        _compose(a, b)


def test_zero_providers_implementing_a_refusing_hook_still_refuses_by_name():
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    only = _Provider("org.only")
    with pytest.raises(SweepValidationError, match="materialize_sweep_case"):
        _compose(only).sweep_materializer.materialize(
            case_dir=None, routed={},
        )


def test_apply_and_target_paths_must_come_from_one_provider():
    """The refusing-hook rule is CROSS-member, not per-member.

    Added 2026-09-20 after the spike. Split across two providers, before-images
    are computed by a different provider than the one mutating, and rollback
    breaks silently. `_OverrideScopeAdapter.target_paths` already enforces this
    for a single plugin; composition must generalise it, not lose it.
    """
    a = _Provider("org.a", apply_overrides=lambda *a, **k: ())
    b = _Provider("org.b", requires=("org.a",),
                  get_override_target_paths=lambda *a, **k: ())
    with pytest.raises(ValueError, match="get_override_target_paths"):
        _compose(a, b)


def test_one_provider_supplying_both_is_accepted():
    both = _Provider(
        "org.both",
        apply_overrides=lambda *a, **k: (),
        get_override_target_paths=lambda *a, **k: (),
    )
    _compose(both)   # must not raise


def test_resolve_and_supported_modes_must_come_from_one_provider():
    """Reclassified 2026-09-23 (R2 finding 2): `get_supported_mutation_modes`
    was `set`-shaped (union across the stack) while `resolve_case_mutation` is
    `single`-shaped (most specific only). A stack where one provider declared
    supported modes and a DIFFERENT, more specific provider implemented the
    resolver composed to the union of both providers' declared modes, so
    `resolve()` could pass a mode into a resolver that never claimed to accept
    it. Reclassified to `single` and paired here, the same guarantee
    `apply_overrides`/`get_override_target_paths` already give.
    """
    a = _Provider("org.a", get_supported_mutation_modes=lambda: frozenset({"synthesize"}))
    b = _Provider("org.b", requires=("org.a",),
                  resolve_case_mutation=lambda *a, **k: None)
    with pytest.raises(ValueError, match="get_supported_mutation_modes"):
        _compose(a, b)


def test_one_provider_supplying_both_modes_and_resolver_is_accepted():
    both = _Provider(
        "org.both",
        resolve_case_mutation=lambda *a, **k: None,
        get_supported_mutation_modes=lambda: frozenset({"clone_and_patch"}),
    )
    _compose(both)  # must not raise


def test_override_scopes_concatenate_across_providers():
    """`get_override_scopes` fits none of the original six shapes.

    Spike finding #1, 2026-09-20. Classified here as a concatenating sequence:
    scopes an environment provider offers and scopes a solver provider offers
    should BOTH be available, since they address different files. If Task 6
    concludes another shape is right, change this test and record why in the
    spec -- do not leave it unclassified.
    """
    env = _Provider("org.env", get_override_scopes=lambda: ("env-scope",))
    solver = _Provider("org.solver", requires=("org.env",),
                       get_override_scopes=lambda: ("solver-scope",))
    assert _compose(env, solver).override_scopes.scopes() == (
        "env-scope", "solver-scope",
    )


def test_a_case_file_path_declared_twice_is_an_error():
    """Spec §2.1: one fact, one declarer. Tolerance is how two sources of
    truth are born."""
    rule = type("_R", (), {"path": "system/controlDict", "role": "openfoam.control_dict"})()
    env = _Provider("org.env")
    env.get_profile().case_files = (rule,)
    solver = _Provider("org.solver", requires=("org.env",))
    solver.get_profile().case_files = (rule,)
    with pytest.raises(ValueError, match="system/controlDict"):
        _compose(env, solver)
