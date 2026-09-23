"""`dict_builder.match_dynamic_entry` -- captures a dynamic-path binding,
not just whether one matched.

Added 2026-09-23 (Phase 3, closing Task 2's Gap 2), alongside this module's
pre-existing `is_known_override_driver_path` (a bare membership check with
the same wildcard convention). A caller that must also validate *what was
bound* -- e.g. `omnidriver-cardiacfoam`'s `overrides.py` checking a
per-case `ecgDomains` name against its entry's declared binding domain --
needs the captured groups themselves.
"""

from __future__ import annotations

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.dict_builder import match_dynamic_entry

_ENTRIES = (
    DictEntry(
        driver_path="$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver",
        description="", value_kind="enum", enum_values=("pseudoECG",),
        dynamic_path=True, allowed_bindings={"<name>": None},
    ),
    DictEntry(
        driver_path="$ELECTRO_MODEL_COEFFS.ecgDomains.electrodePositions.<electrode>",
        description="", value_kind="vector3",
        dynamic_path=True, allowed_bindings={"<electrode>": None},
    ),
    DictEntry(
        driver_path="$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.electrodePositions.<electrode>",
        description="", value_kind="vector3",
        dynamic_path=True, allowed_bindings={"<name>": None, "<electrode>": None},
    ),
    DictEntry(
        driver_path="$A.static.key",
        description="", value_kind="scalar",
    ),
)


def test_a_single_placeholder_template_captures_its_binding():
    match = match_dynamic_entry("$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.ecgSolver", _ENTRIES)
    assert match is not None
    entry, binding = match
    assert entry.driver_path == "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver"
    assert binding == {"<name>": "ECG"}


def test_two_placeholder_templates_do_not_collide_by_segment_length():
    """A 4-segment concrete path matches the 4-segment single-placeholder
    template, not the 5-segment two-placeholder one, and vice versa."""
    short_match = match_dynamic_entry(
        "$ELECTRO_MODEL_COEFFS.ecgDomains.electrodePositions.V1", _ENTRIES,
    )
    assert short_match is not None
    assert short_match[0].driver_path == (
        "$ELECTRO_MODEL_COEFFS.ecgDomains.electrodePositions.<electrode>"
    )
    assert short_match[1] == {"<electrode>": "V1"}

    long_match = match_dynamic_entry(
        "$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.electrodePositions.V1", _ENTRIES,
    )
    assert long_match is not None
    assert long_match[0].driver_path == (
        "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.electrodePositions.<electrode>"
    )
    assert long_match[1] == {"<name>": "ECG", "<electrode>": "V1"}


def test_a_non_dynamic_entry_is_never_matched():
    """This function only ever matches `dynamic_path=True` entries -- a
    static entry's own literal path is a plain-dict-lookup's job, not
    this function's, even when the concrete path is an exact match."""
    assert match_dynamic_entry("$A.static.key", _ENTRIES) is None


def test_no_match_returns_none():
    assert match_dynamic_entry("$ELECTRO_MODEL_COEFFS.nowhere.at.all", _ENTRIES) is None
