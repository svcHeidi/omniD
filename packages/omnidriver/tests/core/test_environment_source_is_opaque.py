"""Core passes the environment source through, unread and unchanged
(spec 2026-09-26-core-generality-design.md §2, A1)."""
from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from plugins.conformance_toy import write_toy_native_case
from plugins.e2e_record_plugin import E2ERecordPlugin

_OPAQUE = "not-a-path: {anything} ; what it means is the plugin's"


class _RecordingPlugin(E2ERecordPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, object]] = []

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
        self.seen.append(("diagnostics", environment_source))
        return ()

    def get_loaded_environment(self, *, environment_source=None, driver_context=None):
        self.seen.append(("load", environment_source))
        return super().get_loaded_environment(environment_source=environment_source, driver_context=driver_context)


def test_the_preflight_adapter_hands_the_value_over_unchanged():
    plugin = _RecordingPlugin()
    ctx = driver_context(plugin, source="test")
    ctx.capabilities.environment_preflight.diagnostics(None, environment_source=_OPAQUE, driver_context=ctx)
    ctx.capabilities.environment_preflight.load(environment_source=_OPAQUE, driver_context=ctx)
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


@pytest.mark.parametrize("old", ["explicit_bashrc", "environment_bashrc"])
def test_the_old_keyword_is_refused(old):
    ctx = driver_context(_RecordingPlugin(), source="test")
    with pytest.raises(TypeError, match=old):
        strict_plan("toyTutorial", overrides={}, driver_context=ctx, **{old: "x"})
