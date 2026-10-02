"""The dict-entry document shape is plugin knowledge.

Core serializes; the plugin supplies the vocabulary. A generic OpenFOAM plugin
must therefore emit no cardiacFoam token at all.
"""

from __future__ import annotations

import json

from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin

# Every token that would betray cardiac vocabulary leaking into a generic
# plugin's machine-readable schema.
_CARDIAC_TOKENS = (
    "ELECTRO_MODEL_COEFFS",
    "electroProperties",
    "physicsProperties",
    "ionicModel",
    "monodomainSolverCoeffs",
    "TNNP",
)

def test_generic_dict_entry_catalog_names_no_cardiac_document() -> None:
    """The previous version of this test asserted only on ``.values()``, so a cardiac leak in the *keys* (``physicsProperties``/``electroProperties``) was invisible to it."""
    catalog = driver_context(MinimalTestPlugin(), source="test:override-schema").capabilities.override_schema.dict_entry_catalog()
    blob = json.dumps(catalog)
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"generic dict entry catalog leaked: {leaked}"
    assert all(not value for value in catalog.values()), catalog
