"""Every .par openCARP ships parses, and an empty patch returns it byte for byte."""
from __future__ import annotations

import pytest

from omnidriver.opencarp.par_format import parse_par, patch_par
from opencarp_native import opencarp_tutorials_root

pytestmark = pytest.mark.native_opencarp


def test_every_shipped_par_round_trips():
    files = sorted(opencarp_tutorials_root().rglob("*.par"))
    assert len(files) >= 20, f"expected openCARP's shipped .par files, found {len(files)}"
    for path in files:
        text = path.read_text()
        parse_par(text)
        assert patch_par(text, {}) == text, path
