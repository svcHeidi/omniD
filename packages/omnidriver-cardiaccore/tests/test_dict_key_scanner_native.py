"""cardiacCore's catalog against its own C++ (added 2026-09-28).

The same scanner and allowlist format as cardiacFOAM's (one reality,
``omnidriver.openfoam.dict_keys_scanner``), at the source root the plugin
profile declares: ``<OMNIDRIVER_CARDIACCORE_TREE>/src``. Its first run found
``setCardiacAnatomy``'s ``rvLocalBands`` uncatalogued."""
from __future__ import annotations

import os

import pytest

from cardiaccore_native import native_cardiaccore_tree
from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.openfoam.dict_keys_scanner import strict_dict_key_report

pytestmark = pytest.mark.native_cardiaccore


def test_the_cardiaccore_catalog_matches_its_cxx_reads() -> None:
    native_cardiaccore_tree()
    plugin = CardiacCorePlugin()
    mapping = plugin.get_profile().cxx_mapping
    root = mapping.source_root(os.environ)
    assert root is not None and root.is_dir(), root
    report = strict_dict_key_report(
        root, allowlist_path=mapping.allowlist_path, entries=plugin.get_dict_entries(),
    )
    assert report.status == "ok", report.to_json()
