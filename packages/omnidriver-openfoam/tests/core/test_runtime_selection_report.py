"""``rtst_scanner.runtime_selection_report``: catalogue enum menus against
the selection tables the scan found. The real tree is covered by
cardiacFOAM's native ``test_cxx_scan_native.py``."""
from __future__ import annotations

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.rtst_scanner import runtime_selection_report

_REGISTRATIONS = {"ionicModel": {"TNNP": "TNNP", "Stewart": "Stewart"}}


def _enum(path: str, values: tuple[str, ...]) -> DictEntry:
    return DictEntry(driver_path=path, description="", value_kind="enum", enum_values=values)


def _report(values: tuple[str, ...], mode: str = "strict", registrations=_REGISTRATIONS) -> dict:
    return runtime_selection_report(
        registrations, entries=(_enum("ionicModel", values),),
        mapping={"by_path": {"ionicModel": {"base": "ionicModel", "mode": mode}}},
    )


def test_agreeing_menus_report_nothing_and_show_the_registered_names():
    report = _report(("Stewart", "TNNP"))
    assert report == {"disagreements": [], "uncatalogued": [], "selector_values": {"ionicModel": ["Stewart", "TNNP"]}}


def test_a_registered_name_the_menu_lacks_is_uncatalogued():
    report = _report(("TNNP",))
    assert report["disagreements"] == []
    assert report["uncatalogued"] == [
        {"kind": "menu_value", "path": "ionicModel", "value": "Stewart", "base": "ionicModel", "class": "Stewart"},
    ]
    assert _report(("TNNP",), mode="subset")["uncatalogued"] == []


def test_a_menu_value_no_table_registers_is_a_disagreement_unless_polymorphic():
    assert _report(("Stewart", "TNNP", "Gone"))["disagreements"] == [
        "ionicModel: menu lists ['Gone'], which ionicModel does not register",
    ]
    assert _report(("Stewart", "TNNP", "Gone"), mode="polymorphic")["disagreements"] == []
    assert _report(("TNNP",), registrations={})["disagreements"] == [
        "ionicModel: menu drawn from ionicModel, but no addToRunTimeSelectionTable(ionicModel, ...) exists",
    ]


def test_an_unmapped_table_is_uncatalogued_and_a_stale_mapping_is_a_disagreement():
    report = runtime_selection_report(
        _REGISTRATIONS, entries=(_enum("tissue", ("epi",)),),
        mapping={
            "by_path": {"gone.path": {"base": "ionicModel", "mode": "strict"}},
            "not_runtime_selected": {"gone.word": "why"},
            "internal_bases": {"noSuchBase": "why"},
        },
    )
    assert report["disagreements"] == [
        "runtime_selection maps gone.path, which is not a catalogue enum",
        "runtime_selection lists gone.word as not runtime-selected, which is not a catalogue enum",
        "runtime_selection lists noSuchBase as internal, but no table registers it",
        "tissue: catalogue enum with no runtime_selection classification",
    ]
    unmapped = runtime_selection_report(_REGISTRATIONS, entries=(), mapping={})["uncatalogued"]
    assert unmapped == [{"kind": "selection_table", "base": "ionicModel", "values": ["Stewart", "TNNP"]}]
