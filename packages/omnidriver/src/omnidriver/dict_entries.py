from __future__ import annotations

from typing import TYPE_CHECKING
from .core.contracts.dictionary import DictEntry, Phase, build_group
if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

# Ionic models that implement transmural tissue heterogeneity
# (configureIonicHeterogeneity, endo/M/epi blend and/or namedRegions) on
# CPU and/or GPU.

def get_heterogeneity_models(
    driver_context: "DriverContext | None" = None,
) -> tuple[str, ...]:
    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    return driver_context.capabilities.manifest.manifest().get("heterogeneity_models", ())

def get_electro_property_entry_groups(
    driver_context: "DriverContext | None" = None,
) -> dict[str, tuple[DictEntry, ...]]:
    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    return driver_context.capabilities.dictionaries.groups()

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
