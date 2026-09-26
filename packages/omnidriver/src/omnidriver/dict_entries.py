"""Core's solver-neutral view of the stack's dictionary vocabulary.

Corrected 2026-09-26 (spec 2026-09-26-core-generality-design.md §2, A6):
``get_heterogeneity_models`` and ``get_electro_property_entry_groups``
lived here. They are cardiac vocabulary and moved to
``omnidriver.cardiacfoam.dict_entries``. ``DictEntry`` and ``build_group``
stay re-exported for existing importers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from .core.contracts.dictionary import DictEntry, build_group
if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

__all__ = ["DictEntry", "all_documented_driver_paths", "build_group"]


def all_documented_driver_paths(
    driver_context: "DriverContext | None" = None,
) -> tuple[str, ...]:
    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    paths = [
        entry.driver_path
        for entry in driver_context.capabilities.dictionaries.entries()
    ]
    return tuple(dict.fromkeys(paths))
