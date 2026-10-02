"""cardiacCore composes its OpenFOAM environment; it does not embed one."""

import inspect

from omnidriver.cardiaccore.plugin import CardiacCorePlugin


def test_the_plugin_no_longer_embeds_an_environment_adapter():
    source = inspect.getsource(CardiacCorePlugin)
    assert "OpenFOAMEnvironmentPlugin()" not in source, (
        "a provider must not embed another provider"
    )
    assert "_openfoam" not in source
