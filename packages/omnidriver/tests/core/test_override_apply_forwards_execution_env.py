"""The composed override path must carry the execution environment.

`_OverrideScopeAdapter.apply` accepted `execution_env` and forwarded it only to
the legacy fallback. Every real adapter implements `apply_overrides`, so on the
path that actually runs, the environment was dropped -- and the OpenFOAM
implementation returns an empty evidence tuple when it is absent. A required
post-write readback was therefore satisfied by having no evidence at all.

Phase 2 makes that readback blocking, which is why this is a prerequisite: an
empty tuple must not be able to pass a check it never performed.
"""

from pathlib import Path

import pytest

from omnidriver.core import plugin_capabilities


class _RecordingPlugin:
    plugin_id = "org.recording"

    def __init__(self):
        self.seen = None

    def apply_overrides(self, overrides, *, case_root, driver_context, execution_env=None):
        self.seen = execution_env
        return ({"driver_path": "a", "matches_requested": True},)


def test_the_environment_reaches_the_plugin_hook():
    plugin = _RecordingPlugin()
    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=plugin)
    adapter.apply(
        [{"driver_path": "a", "value": 1}],
        case_root=Path("/tmp/case"),
        driver_context=object(),
        execution_env={"FOAM_ETC": "/opt/openfoam/etc"},
    )
    assert plugin.seen == {"FOAM_ETC": "/opt/openfoam/etc"}


def test_an_environment_was_supplied_but_no_evidence_returned_is_refused():
    """"I applied it and can say nothing about the result" is not a pass."""

    class _Silent(_RecordingPlugin):
        def apply_overrides(self, overrides, *, case_root, driver_context, execution_env=None):
            return ()

    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_Silent())
    with pytest.raises(ValueError, match="no effective-value evidence"):
        adapter.apply(
            [{"driver_path": "a", "value": 1}],
            case_root=Path("/tmp/case"),
            driver_context=object(),
            execution_env={"FOAM_ETC": "/opt/openfoam/etc"},
        )


def test_no_environment_supplied_still_returns_whatever_the_hook_reports():
    """Offline application must keep working; it simply proves nothing."""
    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_RecordingPlugin())
    records = adapter.apply(
        [{"driver_path": "a", "value": 1}],
        case_root=Path("/tmp/case"),
        driver_context=object(),
    )
    assert records == ({"driver_path": "a", "matches_requested": True},)
