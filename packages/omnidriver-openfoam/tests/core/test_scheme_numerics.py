"""The numerics OpenFOAM's authors state of a scheme, attached to the scheme's menu value: each recorded as stated, with its source."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from omnidriver.openfoam.fv_schemes import FV_SCHEMES_ENTRIES_BY_PATH, ddt_stability_limits
from omnidriver.openfoam.record_key_validation import listed_entry
from omnidriver.openfoam.scheme_tables import committed_menus

_SOURCE = Path(__file__).parent / "fixtures" / "openfoam_v2412_src"
_ATTRIBUTED = [
    (table, name, attributes)
    for table in ("ddtSchemes", "gradSchemes", "divSchemes", "laplacianSchemes", "snGradSchemes", "interpolationSchemes")
    for name, attributes in FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.default"].menu_attributes.items()
]


def test_the_schemes_the_manufactured_cases_use_are_attributed():
    attributed = {(table, name) for table, name, _ in _ATTRIBUTED}
    assert {
        ("ddtSchemes", "backward"), ("ddtSchemes", "Euler"), ("ddtSchemes", "steadyState"), ("gradSchemes", "Gauss"),
        ("gradSchemes", "leastSquares"), ("laplacianSchemes", "Gauss"), ("divSchemes", "Gauss"), ("snGradSchemes", "corrected"),
        ("snGradSchemes", "uncorrected"), ("interpolationSchemes", "linear"),
    } <= attributed


@pytest.mark.parametrize("table,name,attributes", _ATTRIBUTED)
def test_every_attributed_value_is_a_name_the_table_registers(table, name, attributes):
    assert name in committed_menus()["tables"][table]


@pytest.mark.parametrize("table,name,attributes", _ATTRIBUTED)
def test_an_order_is_recorded_as_stated_with_a_source_and_never_as_settled(table, name, attributes):
    assert attributes["settled_by"] is None
    assert attributes["stated_by"], f"{table}.{name} has no source"
    assert all(source["kind"] in {"header", "source", "citation"} for source in attributes["stated_by"])
    for order in attributes.get("formal_order", {}).values():
        assert isinstance(order, int) and order >= 1
    assert set(attributes.get("formal_order", {})) <= {"space", "time"}


@pytest.mark.parametrize("table,name,attributes", _ATTRIBUTED)
def test_a_quoted_line_of_a_header_or_source_is_in_the_file_it_names(table, name, attributes):
    for source in attributes["stated_by"]:
        if source["kind"] == "citation":
            assert source["locator"] is None and source["checked_by_omnid"] is False
            continue
        flat = re.sub(r"\s+", " ", (_SOURCE / source["file"].removeprefix("src/")).read_text())
        assert re.sub(r"\s+", " ", source["text" if source["kind"] == "header" else "excerpt"]) in flat, source


def test_the_cited_headers_say_what_the_orders_rest_on():
    ddt = FV_SCHEMES_ENTRIES_BY_PATH["ddtSchemes.default"].menu_attributes
    assert ddt["backward"]["formal_order"] == {"time": 2} and ddt["Euler"]["formal_order"] == {"time": 1}
    assert "formal_order" not in ddt["steadyState"]
    grad = FV_SCHEMES_ENTRIES_BY_PATH["gradSchemes.default"].menu_attributes
    assert {name: attributes["formal_order"] for name, attributes in grad.items()} == {
        "Gauss": {"space": 2}, "iterativeGauss": {"space": 2}, "leastSquares": {"space": 2},
    }


def test_the_citations_are_for_the_schemes_whose_header_states_no_order():
    for table, name in (("snGradSchemes", "corrected"), ("snGradSchemes", "uncorrected"), ("interpolationSchemes", "linear")):
        kinds = {s["kind"] for s in FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.default"].menu_attributes[name]["stated_by"]}
        assert "citation" in kinds


def test_the_stability_limits_of_the_ddt_schemes_are_read_from_their_attributes():
    assert ddt_stability_limits() == {"Euler": 2.0, "backward": 4.0}


def test_a_listing_carries_the_attributes_beside_the_menu():
    listed = listed_entry("system/fvSchemes", "ddtSchemes.default", FV_SCHEMES_ENTRIES_BY_PATH["ddtSchemes.default"])
    assert listed["menu_attributes"]["backward"]["formal_order"] == {"time": 2}
    assert set(listed["menu_attributes"]) <= set(listed["menu"])
