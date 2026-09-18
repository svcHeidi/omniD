"""Empty environment fixture for tests that require no adapter convention.

This module intentionally provides no OpenFOAM paths, roles, entrypoints,
outputs, parsers, or command declarations.  A Core test that needs any of
those must declare a test-specific capability at the point it is consumed.
OpenFOAM parsing and conventions belong in the OpenFOAM package's tests.
"""

from __future__ import annotations

from plugins.minimal_plugin import MinimalTestPlugin


class NeutralEnvironmentPlugin(MinimalTestPlugin):
    """Named neutral fixture retained while dependent tests are migrated."""

    @property
    def plugin_id(self) -> str:
        return "org.driverfoam.test-neutral-environment"
