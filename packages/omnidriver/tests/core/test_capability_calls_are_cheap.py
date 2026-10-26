"""Capability accessors must be cheap enough to call at context construction."""


def test_the_capability_manifest_is_never_a_shared_copy():
    from omnidriver.core.capability_manifest import capability_manifest
    from omnidriver.core.plugin_interface import driver_context
    from plugins.toy import ToyProvider

    context = driver_context(ToyProvider(), source="test")
    first = capability_manifest(context)
    second = capability_manifest(context)
    assert first == second
    assert first is not second
