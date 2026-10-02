"""Duplicate intakes that composition removed."""

from __future__ import annotations

import pytest


@pytest.fixture
def stack_context():
    """A composed :class:`DriverContext` over the real, installed OpenFOAM environment adapter and :class:`CardiacCorePlugin`."""
    pytest.importorskip("omnidriver.cardiaccore")
    pytest.importorskip("omnidriver.openfoam")
    from omnidriver.cardiaccore.plugin import CardiacCorePlugin
    from omnidriver.core.plugin_interface import driver_context
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    return driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test:deferred-duplicate-intakes",
    )


def test_core_builds_the_capability_manifest(stack_context):
    """The plugin must not assemble what core can compose."""
    import inspect
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    source = inspect.getsource(CardiacFoamPlugin.get_capabilities)
    assert "build_capability_manifest" not in source
