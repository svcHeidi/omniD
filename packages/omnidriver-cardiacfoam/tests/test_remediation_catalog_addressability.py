"""Every STATIC_REMEDIATION_HINTS driver_path must resolve against the live
catalog, so a hint never points an agent at a key the driver cannot set."""

from __future__ import annotations

from omnidriver.core.runtime.remediation import STATIC_REMEDIATION_HINTS, RemediationHint
from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.common_dict_entries import (
    CONTROL_DICT_ENTRIES,
    PHYSICS_PROPERTY_ENTRIES,
)

# Two adapters are installed side by side, so there is no ambient default left
# to discover. The catalog these hints are checked against is cardiacFoam's.
_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:remediation_catalog_addressability",
)

_PREFIX = "$ELECTRO_MODEL_COEFFS."


def _addressable_leaves() -> set[str]:
    leaves: set[str] = set()
    for e in CONTROL_DICT_ENTRIES:
        leaves.add(e.driver_path)
    for e in PHYSICS_PROPERTY_ENTRIES:
        leaves.add(e.driver_path)
    for group in get_electro_property_entry_groups(_CTX).values():
        for e in group:
            dp = e.driver_path
            leaves.add(dp[len(_PREFIX):] if dp.startswith(_PREFIX) else dp)
    return leaves


def _all_hints() -> list[RemediationHint]:
    hints: list[RemediationHint] = []
    for group in STATIC_REMEDIATION_HINTS.values():
        hints.extend(group)
    return hints


def test_every_hint_driver_path_is_catalog_addressable():
    leaves = _addressable_leaves()
    for h in _all_hints():
        if not h.driver_path:        # advisory hints are exempt
            continue
        assert h.driver_path in leaves, (
            f"hint for {h.diagnostic_code or h.source!r} targets non-catalog "
            f"driver_path {h.driver_path!r}"
        )
