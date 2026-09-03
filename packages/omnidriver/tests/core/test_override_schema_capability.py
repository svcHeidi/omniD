"""The config-schema prose and dict-entry document shape are plugin knowledge.

Core assembles and serializes; the plugin supplies the vocabulary. A generic
OpenFOAM plugin must therefore emit no cardiacFoam token at all.
"""

from __future__ import annotations

import json

from omnidriver.core.plugin_interface import generic_openfoam_context

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

_MAKE_SPEC_INFO = {"parameters": {"ionic_models": {"default": ["TNNP"]}}}


def test_generic_config_schema_mentions_no_cardiac_tokens() -> None:
    schema = generic_openfoam_context().capabilities.override_schema.config_schema(
        "someTutorial", _MAKE_SPEC_INFO
    )
    blob = json.dumps(schema)
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"generic config schema leaked cardiac tokens: {leaked}"


def test_generic_dict_entry_catalog_names_no_cardiac_document() -> None:
    """The previous version of this test asserted only on ``.values()``, so a
    cardiac leak in the *keys* (``physicsProperties``/``electroProperties``)
    was invisible to it. Scan the whole structure."""
    catalog = generic_openfoam_context().capabilities.override_schema.dict_entry_catalog()
    blob = json.dumps(catalog)
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"generic dict entry catalog leaked: {leaked}"
    assert all(not value for value in catalog.values()), catalog
