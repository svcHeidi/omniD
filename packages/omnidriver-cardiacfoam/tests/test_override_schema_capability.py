"""The cardiac plugin's config-schema prose and dict-entry document shape.

Moved from packages/omnidriver/tests/core/test_override_schema_capability.py:
these assertions name cardiac vocabulary (``$ELECTRO_MODEL_COEFFS``,
``electroProperties``, the ``singleCell`` worked example, the grouped
``electroProperties`` document shape) that only the cardiac plugin supplies.
The generic-plugin tests in that file (which already passed without
cardiacfoam installed, asserting the *absence* of these tokens) stayed in
core.
"""

from __future__ import annotations

import json

from omnidriver.core.plugin_interface import default_driver_context

_MAKE_SPEC_INFO = {"parameters": {"ionic_models": {"default": ["TNNP"]}}}


def test_cardiac_config_schema_keeps_its_documented_tokens() -> None:
    schema = default_driver_context().capabilities.override_schema.config_schema(
        "singleCell", _MAKE_SPEC_INFO
    )
    blob = json.dumps(schema)
    assert "$ELECTRO_MODEL_COEFFS" in blob
    assert "electroProperties" in blob
    # The worked example is tutorial-specific, so the name must be threaded
    # through rather than baked into the plugin.
    assert "singleCell" in schema["worked_example"]["json"]


def test_cardiac_dict_entry_catalog_keeps_its_document_shape() -> None:
    catalog = default_driver_context().capabilities.override_schema.dict_entry_catalog()
    assert "physicsProperties" in catalog
    assert "electroProperties" in catalog
    # physicsProperties is a flat sequence; electroProperties is grouped. That
    # asymmetry is cardiac document knowledge, not a core convention.
    assert isinstance(catalog["electroProperties"], dict)
    assert catalog["electroProperties"], "cardiac plugin must expose entry groups"
