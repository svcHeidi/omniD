"""Compatibility fallbacks are observable and never implicit."""
from __future__ import annotations

from omnidriver.core import compatibility


def test_recorder_captures_a_fallback_call() -> None:
    with compatibility.track_fallback_calls() as calls:
        compatibility.legacy_case_marker(object(), case_root=None)
    assert calls == ["legacy_case_marker"]


def test_recorder_is_empty_when_no_fallback_is_invoked() -> None:
    with compatibility.track_fallback_calls() as calls:
        pass
    assert calls == []


def test_explicit_plugin_calls_no_compatibility_fallback() -> None:
    from plugins.minimal_plugin import MinimalTestPlugin
    from omnidriver.core.plugin_interface import driver_context

    context = driver_context(MinimalTestPlugin(), source="test:minimal")
    with compatibility.track_fallback_calls() as calls:
        context.capabilities.run_document_configuration.schema()
    assert calls == []
