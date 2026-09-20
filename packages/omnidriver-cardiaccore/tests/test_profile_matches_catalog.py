"""The profile and the dict catalogue must agree on which files a case has."""

from pathlib import Path

from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.cardiaccore.catalogs.inputs import DOCUMENTS


def test_every_catalogued_document_has_a_profile_rule():
    profile = load_plugin_profile(
        Path(__file__).resolve().parents[1]
        / "src/omnidriver/cardiaccore/plugin.yaml"
    )
    declared = {rule.path for rule in profile.case_files}
    catalogued = {f"system/{name}" for name in DOCUMENTS}
    missing = sorted(catalogued - declared)
    assert missing == [], (
        "these documents are in the dict catalogue but have no plugin.yaml "
        f"rule: {missing}"
    )
