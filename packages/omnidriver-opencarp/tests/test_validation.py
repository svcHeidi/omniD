"""Validation against the generated catalog (F1, F2, B4, G1)."""
from __future__ import annotations

import pytest

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.opencarp.par_format import ParFormatError
from omnidriver.opencarp.validation import check_indices, record_key_validator


def test_known_keys_get_their_kind():
    assert record_key_validator("nversion.par", ("gregion[0]", "g_il"), 0.2) == ("scalar", True)
    assert record_key_validator("nversion.par", ("tend",), 20.0) == ("scalar", True)
    assert record_key_validator("nversion.par", ("imp_region[0]", "im"), "tenTusscherPanfilov") == ("string", True)
    assert record_key_validator("nversion.par", ("compute_APD",), True) == ("boolean", True)


@pytest.mark.parametrize(("document", "key_path", "value", "named"), [
    ("nversion.par", ("gregion[0]", "g_ill"), 0.2, "gregion[0].g_ill"),        # misspelled
    ("nversion.par", ("compute_APD",), "no", "compute_APD"),                    # F1: not a bool
    ("nversion.par", ("bidomain",), 5, "bidomain"),                             # outside its menu
    ("nversion.par", ("num_stim",), -1, "num_stim"),                           # below its literal min
    ("mesh.pts", ("tend",), 1.0, "mesh.pts"),                                   # not a .par document
])
def test_refusals_name_the_key(document, key_path, value, named):
    with pytest.raises(TutorialRecordError, match=named.replace("[", r"\[").replace("]", r"\]")):
        record_key_validator(document, key_path, value)


def test_whole_array_shorthand_asks_for_elements():
    # +Help lists '-phys_region[Int].ID' as '{ phys_region[PrMelem1].num_IDs x Int }' (B1)
    with pytest.raises(TutorialRecordError, match="element"):
        record_key_validator("x.par", ("phys_region[0]", "ID"), [1, 2, 3])


def test_index_beyond_count_is_refused_F2():
    with pytest.raises(ParFormatError, match=r"stim\[1\].pulse.strength"):
        check_indices("num_stim = 1\nstim[0].pulse.strength = 250\nstim[1].pulse.strength = 999\n")


def test_count_default_applies_when_absent_F7():
    check_indices("stim[1].pulse.strength = 1\n")          # num_stim defaults to 2
    with pytest.raises(ParFormatError, match="num_stim"):
        check_indices("stim[2].pulse.strength = 1\n")


def test_a_string_menu_accepts_its_values_B_I4():
    # ginkgo_exec is openCARP v18.1's one String parameter with a menu.
    assert record_key_validator("nversion.par", ("ginkgo_exec",), "ref") == ("string", True)
    with pytest.raises(TutorialRecordError, match="ginkgo_exec"):
        record_key_validator("nversion.par", ("ginkgo_exec",), "nope")
