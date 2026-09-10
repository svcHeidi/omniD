"""Backward-compatible lazy alias for the relocated OpenFOAM plugin.

New callers import :class:`omnidriver.openfoam.generic_plugin.GenericOpenFOAMPlugin`.
The lazy lookup keeps importing a Core-only wheel neutral; selecting this
OpenFOAM-specific plugin still requires the OpenFOAM adapter.
"""

from __future__ import annotations

__all__ = ["GenericOpenFOAMPlugin"]


def __getattr__(name: str):
    if name != "GenericOpenFOAMPlugin":
        raise AttributeError(name)
    from omnidriver.openfoam.generic_plugin import GenericOpenFOAMPlugin

    return GenericOpenFOAMPlugin
