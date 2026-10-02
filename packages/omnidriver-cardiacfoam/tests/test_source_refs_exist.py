"""Drift guard: catalogue ``source_refs`` must resolve to real files on disk.

A stale ref (a renamed or deleted C++ file) would otherwise fail at runtime when omnidriver opens it for validation rules.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
from omnidriver.cardiacfoam.common_dict_entries import (
    CONTROL_DICT_ENTRIES,
    PHYSICS_PROPERTY_ENTRIES,
)
from conftest import monorepo_root

pytestmark = pytest.mark.skipif(
    monorepo_root is None,
    reason=(
        "Requires the full cardiacFoam monorepo tree (src/). "
        "Clone the full repository to enable drift guard tests."
    ),
)


def _collect_broken_refs(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``[(missing_path, driver_path), ...]`` for every stale ref."""
    broken: list[tuple[str, str]] = []

    def _check_group(entries):
        for entry in entries:
            for ref in entry.source_refs:
                if not (repo_root / ref).is_file():
                    broken.append((ref, entry.driver_path))

    _check_group(PHYSICS_PROPERTY_ENTRIES)
    _check_group(CONTROL_DICT_ENTRIES)
    for group_entries in get_electro_property_entry_groups().values():
        _check_group(group_entries)

    return broken


def _collect_duplicate_refs_within_entry() -> list[tuple[str, str, int]]:
    """Return ``[(driver_path, ref, count), ...]`` for in-tuple duplicates."""
    from collections import Counter

    dups: list[tuple[str, str, int]] = []

    def _check_group(entries):
        for entry in entries:
            c = Counter(entry.source_refs)
            for ref, n in c.items():
                if n > 1:
                    dups.append((entry.driver_path, ref, n))

    _check_group(PHYSICS_PROPERTY_ENTRIES)
    _check_group(CONTROL_DICT_ENTRIES)
    for group_entries in get_electro_property_entry_groups().values():
        _check_group(group_entries)

    return dups


def test_all_source_refs_resolve_to_real_files():
    assert monorepo_root is not None
    broken = _collect_broken_refs(monorepo_root)

    if not broken:
        return

    lines = [
        "Catalogue source_refs point to files that do not exist on disk.",
        "Update the path in the catalogue to the new location, or remove it.",
        "",
    ]
    for ref, driver_path in sorted(broken):
        lines.append(f"  MISSING  {ref}")
        lines.append(f"    referenced by driver_path: {driver_path!r}")

    pytest.fail("\n".join(lines))


def test_no_duplicate_source_refs_within_a_single_entry():
    dups = _collect_duplicate_refs_within_entry()

    if not dups:
        return

    lines = [
        "DictEntry.source_refs tuples contain duplicate paths:",
        "",
    ]
    for driver_path, ref, count in sorted(dups):
        lines.append(f"  driver_path: {driver_path!r}")
        lines.append(f"    duplicated {count}x: {ref}")

    pytest.fail("\n".join(lines))
