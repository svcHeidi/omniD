"""The numerics cardiacFOAM's own keys carry on their menu values: each claim with the source that states it, never as settled."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.numerics import BATCHED_INTEGRATOR, SOLUTION_ALGORITHM, TIME_COUPLING_SCHEME

_SOURCE = Path(__file__).parent / "fixtures" / "cxx"
_KEYS = {
    "timeCouplingScheme": TIME_COUPLING_SCHEME, "solutionAlgorithm": SOLUTION_ALGORITHM, "batchedIntegrator": BATCHED_INTEGRATOR,
}
_ENTRIES = [
    (entry, key) for entry in CardiacFoamPlugin.get_dictionary_catalog().entries for key in _KEYS if entry.driver_path.endswith("." + key)
]


def test_each_numerics_key_carries_its_attributes_on_every_entry_that_offers_its_menu():
    assert {key for _, key in _ENTRIES} == set(_KEYS)
    for entry, key in _ENTRIES:
        assert entry.menu_attributes == _KEYS[key], entry.driver_path
        assert set(entry.menu_attributes) <= set(entry.enum_values)


@pytest.mark.parametrize("key,attributes", [(key, attrs) for key, table in _KEYS.items() for attrs in table.values()])
def test_a_claim_names_where_it_is_stated_and_is_not_settled(key, attributes):
    assert attributes["settled_by"] is None and attributes["stated_by"]
    assert {source["kind"] for source in attributes["stated_by"]} <= {"source", "inferred", "method"}
    assert all(isinstance(order, int) for order in attributes.get("formal_order", {}).values())


@pytest.mark.parametrize("key,source", [
    (key, source) for key, table in _KEYS.items() for attrs in table.values() for source in attrs["stated_by"] if source["kind"] == "source"
])
def test_a_quoted_line_of_the_source_is_in_the_file_it_names(key, source):
    text = (_SOURCE / source["file"].removeprefix("src/")).read_text()
    assert re.sub(r"\s+", " ", source["excerpt"]) in re.sub(r"\s+", " ", text), source


def test_the_descriptions_state_no_order_the_data_now_carries():
    for entry, key in _ENTRIES:
        assert not re.search(r"first[- ]order|second[- ]order|forward-Euler", entry.description), entry.driver_path


def test_an_order_no_author_states_is_labelled_inferred():
    sbdf2 = TIME_COUPLING_SCHEME["sbdf2"]
    assert [s["claim"] for s in sbdf2["stated_by"] if s["kind"] == "inferred"] == ["formal_order"]
    assert sbdf2["composes"]["kind"] == "inferred"
    assert [s["file"] for s in TIME_COUPLING_SCHEME["godunov"]["stated_by"]] == [
        "tutorials/manufacturedSolutions/monodomainPseudoECG/setup/studies/temporalConvergence/README.md",
    ]
