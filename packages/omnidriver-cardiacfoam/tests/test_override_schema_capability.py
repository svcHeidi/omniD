"""The cardiac plugin's dict-entry document shape: cardiac vocabulary
only the cardiac plugin supplies. Core's tests assert the absence of these tokens."""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:override_schema_capability")


def test_cardiac_dict_entry_catalog_keeps_its_document_shape() -> None:
    catalog = _CTX.capabilities.override_schema.dict_entry_catalog()
    assert "physicsProperties" in catalog
    assert "electroProperties" in catalog
    # physicsProperties is a flat sequence; electroProperties is grouped. That
    # asymmetry is cardiac document knowledge, not a core convention.
    assert isinstance(catalog["electroProperties"], dict)
    assert catalog["electroProperties"], "cardiac plugin must expose entry groups"
