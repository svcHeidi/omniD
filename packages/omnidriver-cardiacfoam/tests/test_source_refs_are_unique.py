"""A catalogue entry names each of its ``source_refs`` once."""

from __future__ import annotations

from collections import Counter

from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES


def test_no_duplicate_source_refs_within_a_single_entry():
    groups = [PHYSICS_PROPERTY_ENTRIES, CONTROL_DICT_ENTRIES]
    groups += ELECTRO_PROPERTY_ENTRY_GROUPS.values()
    duplicated = [
        (entry.driver_path, ref, n)
        for entries in groups
        for entry in entries
        for ref, n in Counter(entry.source_refs).items()
        if n > 1
    ]
    assert duplicated == []
