"""cardiacCore's catalogue against its own C++ source, at the source root
the plugin profile declares: the same scan and rules as cardiacFOAM's."""
from __future__ import annotations

import os
import shutil

import pytest

from cardiaccore_native import native_cardiaccore_tree
from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.openfoam.dict_keys_scanner import catalog_report, scan_source

pytestmark = pytest.mark.native_cardiaccore


def _source_root():
    native_cardiaccore_tree()
    root = CardiacCorePlugin.get_profile().cxx_mapping.source_root(os.environ)
    assert root is not None and root.is_dir(), root
    return root


def test_the_cardiaccore_catalog_agrees_with_its_cxx() -> None:
    mapping = CardiacCorePlugin.get_profile().cxx_mapping
    report = catalog_report(
        _source_root(), allowlist_path=mapping.allowlist_path, entries=CardiacCorePlugin().get_dict_entries(),
    )
    assert report.contradictions == (), "\n".join(report.contradictions)


def test_a_utility_dict_read_names_its_document() -> None:
    scan = scan_source(_source_root())
    bands = next(read for read in scan.reads if read.key == "rvLocalBands")
    assert (bands.root, bands.type, bands.default, bands.required) == (
        "document:setCardiacAnatomyDict", "label", "10", False,
    )


def test_a_key_added_to_a_utility_is_accepted_by_its_scanned_type(tmp_path, monkeypatch) -> None:
    from omnidriver.cardiaccore.record_key_validation import record_key_validator

    anchor = '    const scalar multiplier = slabDict.getOrDefault<scalar>("multiplier", 3.0);\n'
    shutil.copytree(_source_root(), tmp_path / "src", ignore=shutil.ignore_patterns("lnInclude", "Make"))
    reader = tmp_path / "src" / "setPurkinjeSlab" / "setPurkinjeSlab.C"
    assert anchor in reader.read_text(), "the native setPurkinjeSlab.C changed; pick another anchor"
    reader.write_text(reader.read_text().replace(
        anchor, anchor + '    const label omnidriverProbe = slabDict.getOrDefault<label>("omnidriverProbe", 1);\n',
    ))
    monkeypatch.setenv("OMNIDRIVER_CARDIACCORE_TREE", str(tmp_path))
    assert record_key_validator("system/setPurkinjeSlabDict", ("omnidriverProbe",), 4) == ("integer", True)
    with pytest.raises(ValueError, match="reads it as label"):
        record_key_validator("system/setPurkinjeSlabDict", ("omnidriverProbe",), 4.5)
    with pytest.raises(KeyError):
        record_key_validator("system/setCardiacAnatomyDict", ("omnidriverProbe",), 4)
