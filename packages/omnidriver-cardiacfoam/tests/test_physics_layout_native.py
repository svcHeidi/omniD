"""physics_layout.json covers every native case, and every region it
resolves exists (spec 2026-09-26 A7, owner amendment). Supplied only
through OMNIDRIVER_NATIVE_TUTORIALS, never discovered."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.physics_layout import _table, physics_type, region_of

pytestmark = pytest.mark.native


def _cases() -> list[Path]:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail("OMNIDRIVER_NATIVE_TUTORIALS is not set; a native test needs it supplied")
    return sorted(
        p.parent.parent for p in Path(value).rglob("constant/physicsProperties")
        if "results" not in p.relative_to(value).parts
    )


def test_every_native_physics_type_has_a_row_and_its_regions_exist():
    cases = _cases()
    assert cases, "no native case found, so this proves nothing"
    split = 0
    for case in cases:
        layout = _table()[physics_type(case)]
        for role in layout.get("regions", {}):
            region = region_of(case, role)
            assert (case / "constant" / region).is_dir(), (case, role, region)
            split += 1
    assert split, "no region-split case found, so the region path is unproved"
