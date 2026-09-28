"""`mutators.check_dictionary_word_is_safe` -- `_format_value`'s security
refusals, reused for a dictionary key or sub-block name, since neither
`update_foam_entry` nor `ensure_foam_dict` routes those through it. See SECURITY.md."""

from __future__ import annotations

import pytest

from omnidriver.openfoam.mutators import check_dictionary_word_is_safe


@pytest.mark.parametrize("word", ["ECG", "V1", "adapterProbe", "myRegion123"])
def test_a_safe_word_passes_unchanged(word):
    assert check_dictionary_word_is_safe(word) == word


def test_a_semicolon_is_refused():
    with pytest.raises(ValueError, match="statement separator"):
        check_dictionary_word_is_safe("ECG;rm -rf")


def test_a_hash_directive_is_refused():
    with pytest.raises(ValueError, match="directive"):
        check_dictionary_word_is_safe("ECG#include")


def test_a_newline_is_refused():
    with pytest.raises(ValueError, match="statement separator"):
        check_dictionary_word_is_safe("ECG\nbanana")
