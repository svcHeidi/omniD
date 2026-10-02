"""cardiacFOAM's own views of its dictionary vocabulary: the ionic-heterogeneity
models and electroProperties groupings are cardiac-specific, so core names
none of them.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from omnidriver.core.contracts.dictionary import DictEntry

if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext


def get_heterogeneity_models(driver_context: "DriverContext") -> tuple[str, ...]:
    """Ionic models that implement transmural tissue heterogeneity
    (configureIonicHeterogeneity, endo/M/epi blend and/or namedRegions) on
    CPU and/or GPU, as the stack's capability manifest declares them."""
    from omnidriver.core.capability_manifest import capability_manifest

    return capability_manifest(driver_context).get("heterogeneity_models", ())


def get_electro_property_entry_groups(
    driver_context: "DriverContext",
) -> dict[str, tuple[DictEntry, ...]]:
    """The stack's dictionary entries, grouped by cardiacFOAM's own group names."""
    return driver_context.stack.call("get_dict_groups")
