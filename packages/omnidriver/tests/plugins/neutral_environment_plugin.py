"""Empty environment fixture for tests that require no adapter convention."""

from __future__ import annotations

from plugins.minimal_plugin import MinimalTestPlugin


class NeutralEnvironmentPlugin(MinimalTestPlugin):
    """Named neutral fixture retained while dependent tests are migrated."""

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.test-neutral-environment"
