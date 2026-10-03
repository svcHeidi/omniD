"""The plugin contract: one member table, every member optional, refusals by name."""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from pathlib import Path

import pytest

from omnidriver.core import plugin_interface, provider_stack
from omnidriver.core.plugin_interface import DriverContext, SolverPlugin, driver_context, validate_plugin
from omnidriver.core.provider_stack import MEMBERS, MemberAbsent, Needed


class _Bare:
    plugin_name = "Bare"
    plugin_id = "org.test.bare"
    plugin_version = "1"
    plugin_api_version = "2"


def _protocol_members() -> set[str]:
    return {
        name for name, value in vars(SolverPlugin).items()
        if not name.startswith("_") and inspect.isfunction(value)
    }


def test_the_protocol_and_the_member_table_name_the_same_members():
    assert _protocol_members() == set(MEMBERS)
    assert set(SolverPlugin.__annotations__) == set(plugin_interface.IDENTITY_MEMBERS)


def test_every_member_has_a_shape_and_an_absent_answer():
    shapes = {"set", "map", "catalog", "sequence", "single", "chain", "profile"}
    for member, (shape, absent) in MEMBERS.items():
        assert shape in shapes, member
        assert absent is None or isinstance(absent, Needed) or (
            callable(absent) and not inspect.signature(absent).parameters
        ), member


def test_no_fallback_reaches_cardiac_code_at_all():
    """The stack's only fallbacks are the absent answers in its member table:
    each takes no argument, so it cannot see which provider is missing, and
    the module that holds them imports nothing outside core."""
    tree = ast.parse(Path(provider_stack.__file__).read_text())
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0
    ] + [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert [name for name in imported if name.startswith("omnidriver")] == []
    for member, (_shape, absent) in MEMBERS.items():
        if callable(absent):
            assert not inspect.signature(absent).parameters, member


def test_a_provider_with_only_its_identity_joins_a_stack_and_every_neutral_member_answers(tmp_path):
    context = driver_context(_Bare(), source="test")
    stack = context.stack
    assert stack.call("get_profile").case_files == ()
    assert stack.call("get_profile").cxx_mapping is None
    assert stack.call("get_solver_commands") == frozenset()
    assert stack.call("get_tutorial_records") == {}
    assert stack.call("get_dict_entries") == ()
    assert stack.call("get_dictionary_catalog").documents == {}
    assert stack.call("get_dict_key_scanner") is None
    assert stack.call("get_configured_environment", {"A": "1"}, context) == {"A": "1"}
    assert stack.call("get_case_runtime_conventions").generated_file_names == ()
    [unavailable] = stack.call("get_environment_diagnostics", None)
    assert unavailable.code == "environment_capability_unavailable"
    assert stack.call("validate_run_semantics", tmp_path) == ()


@pytest.mark.parametrize("member", sorted(m for m, (_s, a) in MEMBERS.items() if isinstance(a, Needed)))
def test_a_needed_member_refuses_by_name_with_its_operation(member):
    stack = driver_context(_Bare(), source="test").stack
    with pytest.raises(MemberAbsent, match=member) as caught:
        stack.call(member)
    assert MEMBERS[member][1].operation in str(caught.value)
    assert "org.test.bare" in str(caught.value)


def test_an_unknown_member_is_refused_at_the_call():
    with pytest.raises(KeyError, match="get_solver_comands"):
        driver_context(_Bare(), source="test").stack.call("get_solver_comands")


def test_a_misspelled_member_is_refused_when_the_provider_joins():
    class Misspelled(_Bare):
        def get_solver_comands(self):
            return frozenset({"x"})

    with pytest.raises(TypeError, match="get_solver_comands is not a plugin contract member"):
        validate_plugin(Misspelled())


def test_a_member_that_is_not_callable_is_refused():
    class Data(_Bare):
        get_solver_commands = frozenset({"x"})

    with pytest.raises(TypeError, match="get_solver_commands must be callable"):
        validate_plugin(Data())


@pytest.mark.parametrize("present", ["resolve_case_mutation", "get_supported_mutation_modes", "render_case_files", "get_rendered_formats"])
def test_half_of_a_pair_is_refused(present):
    half = type("Half", (_Bare,), {present: lambda self, *a, **k: None})
    with pytest.raises(TypeError, match=present):
        validate_plugin(half())


def test_the_stack_hands_back_the_providers_own_callable_and_its_exceptions():
    def read(path, key):
        return "sentinel"

    class Reader(_Bare):
        def get_config_value_reader(self):
            return read

        def validate_configuration(self, spec):
            raise RuntimeError("same failure")

    stack = driver_context(Reader(), source="test").stack
    assert stack.call("get_config_value_reader") is read
    with pytest.raises(RuntimeError, match="same failure"):
        stack.call("validate_configuration", None)


def test_identity_records_which_provider_answers_each_member():
    class Commands(_Bare):
        def get_solver_commands(self):
            return frozenset({"x"})

    resolutions = driver_context(Commands(), source="test").identity.resolutions
    assert set(resolutions) == set(MEMBERS)
    assert resolutions["get_solver_commands"] == "org.test.bare"
    assert resolutions["get_tutorial_records"] == provider_stack.UNCLAIMED


def test_a_driver_context_holds_providers_identity_selector_and_repository_only():
    plugin = _Bare()
    context = driver_context(plugin, source="test")
    rebuilt = DriverContext((plugin,), context.identity)
    assert [item.name for item in fields(rebuilt)] == ["providers", "identity", "plugin_selector", "repository"]
    assert rebuilt == context
    assert rebuilt.stack.ids == ("org.test.bare",)
