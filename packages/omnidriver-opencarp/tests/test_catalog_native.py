"""Drift gate: the committed catalog is exactly what the installed binary says."""
from __future__ import annotations

import json
from importlib import resources

import pytest

from omnidriver.opencarp.catalog_generation import build_catalog
from opencarp_native import require_opencarp_binary

pytestmark = pytest.mark.native_opencarp


def test_committed_catalog_matches_the_binary():
    require_opencarp_binary()
    committed = json.loads(resources.files("omnidriver.opencarp").joinpath("opencarp_parameters.json").read_text())
    assert build_catalog() == committed, "regenerate: python scripts/generate-opencarp-catalog.py"
