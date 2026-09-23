"""`mutators.check_dictionary_word_is_safe` -- `_format_value`'s security
refusals, reused for a dictionary KEY or sub-block name rather than a value.

Added 2026-09-23 (Phase 3, closing Task 2's Gap 2). A dynamic-path binding
bound against an explicitly open domain becomes a segment of the `key`/
`scope` argument to `update_foam_entry`/`ensure_foam_dict`, and neither of
those routes it through `_format_value` (that only ever inspects the
right-hand-side value) -- so without this, an open binding could carry a
`;` or `#` into a newly-created sub-block name unrefused. See SECURITY.md.
"""

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
