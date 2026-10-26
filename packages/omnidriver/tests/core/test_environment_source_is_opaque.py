"""Core passes the environment source through, unread and unchanged."""
from __future__ import annotations

import os

import pytest

from omnidriver.core.environment_connection import load_environment
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from plugins.toy import write_toy_native_case
from plugins.toy import ToyStack

_OPAQUE = "not-a-path: {anything} ; what it means is the plugin's"


class _RecordingPlugin(ToyStack):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, object]] = []

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
        self.seen.append(("diagnostics", environment_source))
        return ()

    def get_loaded_environment(self, *, environment_source=None, driver_context=None):
        self.seen.append(("load", environment_source))
        return dict(os.environ)


def test_the_preflight_adapter_hands_the_value_over_unchanged():
    plugin = _RecordingPlugin()
    ctx = driver_context(plugin, source="test")
    ctx.stack.call("get_environment_diagnostics", None, environment_source=_OPAQUE, driver_context=ctx)
    load_environment(ctx, _OPAQUE)
    assert plugin.seen == [("diagnostics", _OPAQUE), ("load", _OPAQUE)]


def test_strict_plan_threads_it_to_the_plugin_unchanged(tmp_path):
    plugin = _RecordingPlugin()
    ctx = driver_context(plugin, source="test")
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    strict_plan(
        "toyTutorial", overrides={"cases_root": str(cases_root)}, environment_source=_OPAQUE,
        scratch_root=tmp_path / "scratch", driver_context=ctx,
    )
    assert ("diagnostics", _OPAQUE) in plugin.seen


class _LoadedEnvironmentPlugin(_RecordingPlugin):
    def get_loaded_environment(self, *, environment_source=None, driver_context=None):
        self.seen.append(("load", environment_source))
        return {**os.environ, "LOADED_FROM": str(environment_source)}

    def get_plan_diagnostics(self, case_root, *, workflow_dag, env, scratch_root, driver_context):
        self.seen.append(("plan_diagnostics", env.get("LOADED_FROM")))
        return ()

    def inspect_effective_configuration(self, *, case_root, execution_env, driver_context):
        self.seen.append(("configuration", execution_env.get("LOADED_FROM")))
        return ()


def test_strict_plan_loads_the_environment_once_hands_it_to_every_member_and_records_it(tmp_path):
    plugin = _LoadedEnvironmentPlugin()
    ctx = driver_context(plugin, source="test")
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    report = strict_plan(
        "toyTutorial", overrides={"cases_root": str(cases_root)}, environment_source=_OPAQUE,
        scratch_root=tmp_path / "scratch", driver_context=ctx,
    )
    assert plugin.seen.count(("load", _OPAQUE)) == 1
    assert ("plan_diagnostics", _OPAQUE) in plugin.seen and ("configuration", _OPAQUE) in plugin.seen
    command = report.launch["command"]
    assert command[command.index("--environment-source") + 1] == _OPAQUE


@pytest.mark.parametrize("old", ["explicit_bashrc", "environment_bashrc"])
def test_the_old_keyword_is_refused(old):
    ctx = driver_context(_RecordingPlugin(), source="test")
    with pytest.raises(TypeError, match=old):
        strict_plan("toyTutorial", overrides={}, driver_context=ctx, **{old: "x"})
