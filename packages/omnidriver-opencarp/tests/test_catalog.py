"""The committed catalog, as generated from openCARP v18.1's +Help."""
from __future__ import annotations

from omnidriver.opencarp.catalog import load_catalog, template_name

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


def test_the_record_declares_how_omnidriver_check_exercises_it():
    from omnidriver.opencarp.records import TUTORIAL_RECORDS

    quantity = TUTORIAL_RECORDS["niedererNVersion"].conformance.quantity
    assert quantity.artifact_format and quantity.at is None and quantity.pairs is None


# openCARP v18.1 `+Help dt`, verbatim.
HELP_DT = """
dt:
	Defines the time step size to solve the numeric equations for.
Check the first chapters of the openCARP manual for a comprehensive explanation on how to choose 'dt'. 

	type:	Double
	default:(Double)(5.)
	min:	(Double)(0.)
	units:	microseconds
	Changes the default value of: {
		tsav
	}

"""


def test_a_parameters_units_are_read_from_its_help():
    from omnidriver.opencarp.catalog_generation import parse_help_detail

    detail = parse_help_detail("dt", HELP_DT)
    assert (detail["units"], detail["default"], detail["minimum"], detail["maximum"]) == ("microseconds", "5.", "0.", None)


def test_the_committed_catalog_carries_the_binarys_units():
    p = load_catalog().parameters
    assert (p["dt"].units, p["tend"].units, p["spacedt"].units) == ("microseconds", "ms", "ms")
    assert p["num_stim"].units is None


def test_the_record_key_catalog_lists_each_parameters_unit(tmp_path):
    from omnidriver.opencarp.plugin import OpenCARPPlugin

    (tmp_path / "nversion.par").write_text("")
    listed = {entry["key"]: entry for entry in OpenCARPPlugin().get_record_key_catalog(tmp_path)}
    assert (listed["dt"]["unit"], listed["tend"]["unit"], listed["num_stim"]["unit"]) == ("microseconds", "ms", None)
