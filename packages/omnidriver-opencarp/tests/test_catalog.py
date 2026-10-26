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
    assert (detail["units"], detail["units_as_printed"]) == ("us", "microseconds")
    assert (detail["default"], detail["minimum"], detail["maximum"]) == ("5.", "0.", None)


def test_the_committed_catalog_carries_the_binarys_units_in_cores_spelling():
    p = load_catalog().parameters
    assert (p["dt"].units, p["tend"].units, p["spacedt"].units) == ("us", "ms", "ms")
    assert (p["dt"].units_as_printed, p["stim[Int].elec.radius"].units) == ("microseconds", "um")
    assert p["num_stim"].units is None


def test_a_menu_keeps_what_each_value_means():
    assert load_catalog().parameters["parab_solve"].menu_labels == {
        "0": "Explicit", "1": "Crank-Nicolson", "2": "2nd order dt",
    }


def test_a_literal_default_is_a_value_and_a_c_expression_is_kept_apart():
    p = load_catalog().parameters
    assert (p["compute_APD"].default, p["imp_region[Int].im"].default) == ("0", '"LuoRudy91"')
    assert (p["dump_ecg_leads"].default, p["dump_ecg_leads"].default_expression) == (None, "strlen(phie_rec_ptf)>0?0:1")
    assert p["dt"].default_expression is None


def test_the_record_key_catalog_lists_each_parameters_unit(tmp_path):
    from omnidriver.opencarp.plugin import OpenCARPPlugin

    (tmp_path / "nversion.par").write_text("")
    listed = {entry["key"]: entry for entry in OpenCARPPlugin().get_record_key_catalog(tmp_path, driver_context=None)}
    assert (listed["dt"]["unit"], listed["tend"]["unit"], listed["num_stim"]["unit"]) == ("us", "ms", None)
    assert listed["parab_solve"]["menu_labels"]["1"] == "Crank-Nicolson"
    assert listed["tracedt"]["default_expression"] == "timedt" and listed["tracedt"]["default"] is None
