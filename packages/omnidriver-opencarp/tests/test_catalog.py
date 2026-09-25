"""The committed catalog, as generated from openCARP v18.1's +Help (evidence B1-B5, G6)."""
from __future__ import annotations

from omnidriver.opencarp.catalog import load_catalog, template_name


def test_identity_is_the_binary_and_carries_no_repository_url():
    identity = load_catalog().identity
    assert identity["tag"] == "v18.1"
    assert set(identity) == {"tag", "hash"}      # never the CI URL (G3)


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


def test_all_266_parameters():
    assert len(load_catalog().parameters) == 266
