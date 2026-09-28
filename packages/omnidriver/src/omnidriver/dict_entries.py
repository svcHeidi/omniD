"""Core's solver-neutral view of the stack's dictionary vocabulary.

``DictEntry`` and ``build_group`` are re-exported here for existing importers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from .core.contracts.dictionary import DictEntry, build_group
if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

__all__ = ["DictEntry", "all_documented_driver_paths", "build_group"]


def all_documented_driver_paths(driver_context: "DriverContext") -> tuple[str, ...]:
    paths = [
        entry.driver_path
        for entry in driver_context.capabilities.dictionaries.entries()
    ]
    return tuple(dict.fromkeys(paths))
