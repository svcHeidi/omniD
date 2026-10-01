"""The committed catalog, as generated from openCARP v18.1's +Help."""
from __future__ import annotations

import json
from importlib import resources

from omnidriver.opencarp.catalog import load_catalog, template_name
from omnidriver.opencarp.catalog_generation import compare_catalogs

_COMMITTED = resources.files("omnidriver.opencarp").joinpath("opencarp_parameters.json").read_text()


def test_identity_is_the_binary_and_carries_no_repository_url():
    identity = load_catalog().identity
    assert identity["tag"] == "v18.1"
    assert set(identity) == {"tag", "hash"}      # never the CI URL


def test_template_names():
    assert template_name("stim[0].pulse.strength") == "stim[Int].pulse.strength"
    assert template_name("phys_region[1].ID[3]") == "phys_region[Int].ID[Int]"


def test_known_parameters_B2_B5():
    p = load_catalog().parameters
    assert (p["bidomain"].value_kind, p["bidomain"].default, p["bidomain"].menu) == ("integer", "0", ("2", "1", "0"))
    assert (p["num_stim"].default, p["num_stim"].allocates) == ("2", ("stim", "stimulus"))
    assert p["compute_APD"].value_kind == "boolean"
    assert p["imp_region[Int].im"].value_kind == "string"
    assert p["tend"].minimum == "dt/1000."


def test_whole_array_shorthand_has_no_value_kind():
    p = load_catalog().parameters
    shorthand = [s for s in p.values() if s.opencarp_type.startswith("{")]
    assert shorthand and all(s.value_kind is None for s in shorthand)


def test_a_string_menu_holds_values_not_their_quotes():
    # +Help prints a String menu item as (String)("ref"); the catalog keeps
    # the value a .par assigns, ref, not the C literal "ref".
    menu = load_catalog().parameters["ginkgo_exec"].menu
    assert set(menu) == {"dpcpp", "hip", "cuda", "omp", "ref"}


def test_a_parameter_only_the_binary_lists_is_uncatalogued():
    committed = json.loads(_COMMITTED)
    built = {**committed, "parameters": committed["parameters"] + [{"name": "newParameter", "type": "Float"}]}
    report = compare_catalogs(committed, built)
    assert (report["contradictions"], [p["name"] for p in report["uncatalogued"]]) == ([], ["newParameter"])
    changed = {**committed, "parameters": [{**committed["parameters"][0], "type": "Int"}, *committed["parameters"][1:]]}
    assert compare_catalogs(committed, changed)["contradictions"]
