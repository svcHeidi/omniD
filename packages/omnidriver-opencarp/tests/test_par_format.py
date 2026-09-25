"""The .par rules, each one tied to a line of evidence in docs/solver-learning/opencarp.md."""
from __future__ import annotations

import pytest

from omnidriver.opencarp.par_format import (
    APPENDED_BLOCK_HEADER, ParFormatError, format_value, parse_par, patch_par, read_raw, unquote, values_agree,
)

TEXT = 'num_stim = 1 \nstim[0].name = "S1"\t# label\n# comment\n\ngregion[0].g_il = 0.17\n'


def test_parse_keys_and_raw_values():
    assert [(a.key, a.value) for a in parse_par(TEXT)] == [
        ("num_stim", "1"), ("stim[0].name", '"S1"'), ("gregion[0].g_il", "0.17"),
    ]


def test_whitespace_separator_F9():
    text = "stim[0].elec.p0[2] 0\n"
    assert read_raw(text, "stim[0].elec.p0[2]") == "0"
    assert patch_par(text, {"stim[0].elec.p0[2]": "5"}) == "stim[0].elec.p0[2] 5\n"


def test_last_assignment_wins_F8():
    assert read_raw("spacedt = 1\nspacedt = 2\n", "spacedt") == "2"


def test_patch_in_place_keeps_everything_else():
    patched = patch_par(TEXT, {"gregion[0].g_il": "0.2"})
    assert patched == TEXT.replace("0.17", "0.2")


def test_patch_keeps_an_inline_comment():
    assert patch_par(TEXT, {"stim[0].name": '"S2"'}).splitlines()[1] == 'stim[0].name = "S2"\t# label'


def test_patch_appends_an_absent_key_in_a_marked_block():
    patched = patch_par(TEXT, {"tend": "20.0"})
    assert patched.startswith(TEXT)
    assert patched.endswith(f"\n{APPENDED_BLOCK_HEADER}\ntend = 20.0\n")


def test_patch_is_idempotent():
    once = patch_par(TEXT, {"tend": "20.0"})
    assert patch_par(once, {"tend": "20.0"}) == once


def test_patch_refuses_a_repeated_key_F8():
    with pytest.raises(ParFormatError, match="spacedt"):
        patch_par("spacedt = 1\nspacedt = 2\n", {"spacedt": "3"})


def test_unparseable_line_is_refused_by_line_number():
    # Any "<key><space><value>" is valid syntax (F9), so only a line with no
    # key at its start is malformed.
    with pytest.raises(ParFormatError, match="line 2"):
        parse_par("a = 1\n= 5\n")


@pytest.mark.parametrize(("value", "kind", "text"), [
    (True, "boolean", "1"), (False, "boolean", "0"),       # F1: only 0 and false mean off
    (3, "integer", "3"), (0.17, "scalar", "0.17"), (500, "scalar", "500.0"),
    ("tenTusscherPanfilov", "string", "tenTusscherPanfilov"), ("flags=EPI", "string", "flags=EPI"),
    ("two words", "string", '"two words"'), ("", "string", '""'),
])
def test_format_value(value, kind, text):
    assert format_value(value, kind) == text


def test_format_refuses_a_non_bool_flag():
    with pytest.raises(ParFormatError):
        format_value("no", "boolean")


def test_values_agree_numerically_and_unquoted():
    assert values_agree("scalar", 0.001, "1e-3")
    assert values_agree("integer", 2, "2")
    assert values_agree("string", "S1", '"S1"')
    assert values_agree("boolean", True, "1") and not values_agree("boolean", True, "0")
    assert not values_agree("scalar", 0.2, None)


def test_unquote():
    assert unquote('"S1"') == "S1" and unquote("S1") == "S1"


@pytest.mark.parametrize("text", ["x\nnum_stim = 0", "x\rnum_stim = 0", "a\tb", "nul\x00", "bell\x07", "del\x7f"])
def test_format_refuses_a_control_character_B_I5(text):
    # A study value (an RFile name, say) must not be able to add a .par line:
    # "x\nnum_stim = 0" used to be spelled '"x\nnum_stim = 0"', and patch_par
    # then wrote a second assignment, num_stim = 0".
    with pytest.raises(ParFormatError, match="control character") as excinfo:
        format_value(text, "string")
    assert repr(text) in str(excinfo.value)


def test_the_num_stim_injection_no_longer_reaches_the_case_B_I5():
    with pytest.raises(ParFormatError):
        patch_par(TEXT, {"stim[0].name": format_value("x\nnum_stim = 0", "string")})
    assert read_raw(TEXT, "num_stim") == "1"


@pytest.mark.parametrize("spelled", ["2\nc = 3", "2\rc = 3", '"x\nnum_stim = 0"'])
def test_patch_refuses_a_value_with_a_line_break_B_I5(spelled):
    # Defence in depth: patch_par takes values already spelled, so it checks too.
    with pytest.raises(ParFormatError, match="line break"):
        patch_par("b = 1\n", {"b": spelled})
    with pytest.raises(ParFormatError, match="line break"):
        patch_par("b = 1\n", {"absent": spelled})
