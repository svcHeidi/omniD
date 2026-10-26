from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


def test_cardiac_profile_declares_case_files_and_cxx_provenance() -> None:
    profile = CardiacFoamPlugin().get_profile()

    assert profile.plugin_id == "org.cardiacfoam"
    # `system/controlDict` is declared by the environment provider, not here: one declarer per path.
    assert {rule.path for rule in profile.case_files} >= {
        "constant/physicsProperties",
        "constant/electroProperties",
    }
    assert profile.cxx_mapping is not None
    assert profile.cxx_mapping.allowlist_path.is_file()
    assert profile.digest.startswith("sha256:")


def test_cardiac_profile_source_root_is_supplied_never_guessed(tmp_path: Path) -> None:
    """The C++ source is ``<OMNIDRIVER_NATIVE_TUTORIALS>/../src``, and there is none when nothing is supplied."""
    mapping = CardiacFoamPlugin().get_profile().cxx_mapping
    assert mapping.source_root({}) is None
    tutorials = tmp_path / "tutorials"
    assert mapping.source_root({"OMNIDRIVER_NATIVE_TUTORIALS": str(tutorials)}) == tmp_path / "src"


def test_cardiac_catalog_partitions_entries_by_document() -> None:
    catalog = CardiacFoamPlugin().get_dictionary_catalog()

    assert {"electroProperties", "physicsProperties", "prePacingProperties"} <= set(catalog.documents)
    assert "controlDict" not in catalog.documents
    assert {entry.driver_path for entry in catalog.entries_for("physicsProperties")} == {"type"}
    assert {entry.driver_path for entry in catalog.entries_for("prePacingProperties")} >= {
        "$PRE_PACING.tolerance", "$PRE_PACING.minBeats", "$PRE_PACING.maxBeats", "$PRE_PACING.beatComparisonInterval",
        "$PRE_PACING.singleCellIonicModel",
    }
