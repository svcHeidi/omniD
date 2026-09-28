"""cardiacFOAM's own views of its dictionary vocabulary: the ionic-heterogeneity
models and electroProperties groupings are cardiac-specific, so core names
none of them.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from omnidriver.core.contracts.dictionary import DictEntry

if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext


def get_heterogeneity_models(
    driver_context: "DriverContext | None" = None,
) -> tuple[str, ...]:
    """Ionic models that implement transmural tissue heterogeneity
    (configureIonicHeterogeneity, endo/M/epi blend and/or namedRegions) on
    CPU and/or GPU, as the stack's capability manifest declares them."""
    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    return driver_context.capabilities.manifest.manifest().get("heterogeneity_models", ())


def get_electro_property_entry_groups(
    driver_context: "DriverContext | None" = None,
) -> dict[str, tuple[DictEntry, ...]]:
    """The stack's dictionary entries, grouped by cardiacFOAM's own group names."""
    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    return driver_context.capabilities.dictionaries.groups()
