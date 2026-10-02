"""The committed catalog against the installed binary: every committed
claim holds (a parameter only the binary lists is uncatalogued, not a
failure)."""
from __future__ import annotations

import json
from importlib import resources

import pytest

from omnidriver.opencarp.catalog_generation import build_catalog, compare_catalogs
from opencarp_native import require_opencarp_binary

pytestmark = pytest.mark.native_opencarp


def test_the_binary_refutes_no_committed_claim():
    require_opencarp_binary()
    committed = json.loads(resources.files("omnidriver.opencarp").joinpath("opencarp_parameters.json").read_text())
    report = compare_catalogs(committed, build_catalog())
    assert report["contradictions"] == [], "regenerate: python scripts/generate-opencarp-catalog.py"

