"""A catalogue entry names each of its ``source_refs`` once."""

from __future__ import annotations

from collections import Counter

from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES, PHYSICS_PROPERTY_ENTRIES
from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
from omnidriver.core.plugin_interface import load_plugin_context


def test_no_duplicate_source_refs_within_a_single_entry():
    groups = [PHYSICS_PROPERTY_ENTRIES, CONTROL_DICT_ENTRIES]
    groups += get_electro_property_entry_groups(load_plugin_context("cardiacfoam")).values()
    duplicated = [
        (entry.driver_path, ref, n)
        for entries in groups
        for entry in entries
        for ref, n in Counter(entry.source_refs).items()
        if n > 1
    ]
    assert duplicated == []
