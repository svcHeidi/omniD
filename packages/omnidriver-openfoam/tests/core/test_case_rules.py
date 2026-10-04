"""The catalogue's conditional logic over a resolved dictionary."""

from __future__ import annotations

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.case_rules import flatten, read_leaves, rule_diagnostics


def _entry(path, **fields):
    return DictEntry(driver_path=path, description="d", **{"value_kind": "word", **fields})


def _violations(entries, context):
    return {(item.field, item.message) for item in rule_diagnostics(entries, context, document="doc")}


def test_a_required_key_is_reported_only_while_it_applies():
    entries = [
        _entry("$S.mode"),
        _entry("$S.depth", required=True, applicable_when={"mode": "deep"}),
    ]
    assert _violations(entries, {"mode": "deep"}) == {("depth", "depth is required.")}
    assert _violations(entries, {"mode": "flat"}) == set()
    assert _violations(entries, {"mode": "deep", "depth": 3}) == set()


def test_a_conditional_requirement_names_its_condition():
    entries = [_entry("$S.limit", required=True, required_when={"solver": ("rk", "euler")})]
    assert _violations(entries, {"solver": "euler"}) == {("limit", "limit is required when solver in (rk, euler).")}
    assert _violations(entries, {"solver": "other"}) == set()
    assert _violations(entries, {}) == set()


def test_a_forbidden_key_is_reported_when_set_and_never_required():
    entries = [_entry("$S.tol", required=True, forbidden_when={"mode": "exact"})]
    assert _violations(entries, {"mode": "exact"}) == set()
    assert _violations(entries, {"mode": "exact", "tol": 1e-3}) == {("tol", "tol is forbidden when mode=exact.")}


def test_exclusion_and_co_requirement_are_judged_from_the_key_that_declares_them():
    entries = [
        _entry("$S.lineEnd", mutually_exclusive_with=("$S.initDir",)),
        _entry("$S.initDir"),
        _entry("$S.low", co_required_with=("$S.high",)),
        _entry("$S.high", co_required_with=("$S.low",)),
    ]
    assert _violations(entries, {"lineEnd": "(0 0 1)", "initDir": "(1 0 0)"}) == {
        ("lineEnd", "lineEnd is mutually exclusive with initDir."),
    }
    assert _violations(entries, {"low": 1}) == {("low", "low requires high to be set as well.")}
    assert _violations(entries, {"low": 1, "high": 2}) == set()


def test_one_of_a_group_is_required_and_reported_once_while_the_group_applies():
    entries = [
        _entry("$S.box.max", required_one_of=("$S.box.maxList",), applicable_when={"box.$present": True}),
        _entry("$S.box.maxList", required_one_of=("$S.box.max",), applicable_when={"box.$present": True}),
    ]
    present = {"box.$present": True, "box.min": 1}
    assert _violations(entries, present) == {("box.max", "one of box.max, box.maxList is required.")}
    assert _violations(entries, {**present, "box.maxList": [1]}) == set()
    assert _violations(entries, {**present, "box.max": 1}) == set()
    assert _violations(entries, {"box.min": 1}) == set()


def test_one_of_a_group_is_judged_in_each_instance_of_a_block():
    entries = [
        _entry("$S.nets.<name>.edges", required_one_of=("$S.nets.<name>.edgeList",)),
        _entry("$S.nets.<name>.edgeList", required_one_of=("$S.nets.<name>.edges",)),
        _entry("$S.nets.<name>.kind"),
    ]
    context = {"nets.a.kind": "x", "nets.b.kind": "y", "nets.b.edges": 1}
    assert _violations(entries, context) == {("nets.a.edges", "one of nets.a.edgeList, nets.a.edges is required.")}


def test_a_switch_is_compared_by_meaning_not_spelling():
    entries = [_entry("$S.scale", required=True, applicable_when={"enabled": "true"})]
    assert _violations(entries, {"enabled": True}) == {("scale", "scale is required.")}
    assert _violations(entries, {"enabled": False}) == set()


def test_each_instance_of_a_block_is_judged_on_its_own_values():
    entries = [
        _entry("$S.nets.<name>.kind"),
        _entry("$S.nets.<name>.cv", required=True, applicable_when={"nets.<name>.kind": "fast"}),
    ]
    context = {"nets.a.kind": "fast", "nets.b.kind": "slow", "nets.c.kind": "fast", "nets.c.cv": 4.0}
    assert _violations(entries, context) == {("nets.a.cv", "nets.a.cv is required.")}


def test_a_literal_the_catalogue_uses_beside_a_block_is_not_an_instance():
    entries = [
        _entry("$S.ecg.<name>.solver", required=True),
        _entry("$S.ecg.electrodes.<electrode>"),
    ]
    assert _violations(entries, {"ecg.electrodes.V1": "(0 0 0)", "ecg.main.other": 1}) == {
        ("ecg.main.solver", "ecg.main.solver is required."),
    }


def test_a_value_outside_the_menu_is_refused_and_a_value_inside_is_not():
    entries = [_entry("$S.model", value_kind="enum", enum_values=("a", "b"))]
    assert _violations(entries, {"model": "b"}) == set()
    assert _violations(entries, {"model": "c"}) == {
        ("model", "model is 'c', not one of the values the catalogue lists: ['a', 'b']."),
    }


def test_leaves_are_read_through_blocks(tmp_path):
    path = tmp_path / "dict"
    path.write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; object dict; }\n"
        "top 1;\nblock { inner { leaf yes; } other word; }\n"
    )
    assert read_leaves(path) == {"top": 1, "block.inner.leaf": True, "block.other": "word"}
    assert read_leaves(path, ("block",)) == {"inner.leaf": True, "other": "word"}
    assert flatten({"a": {"b": 1}, None: 2}) == {"a.b": 1}


def test_a_listing_shows_the_relations_a_case_is_judged_by_and_omits_what_an_entry_leaves_empty():
    from omnidriver.openfoam.record_key_validation import listed_entry

    entry = _entry(
        "$S.depth", required=True, required_when={"mode": ("deep", "abyssal")}, mutually_exclusive_with=("$S.height",),
        notes="metres", examples=("3",),
    )
    listing = listed_entry("system/dict", "depth", entry)
    assert listing["required"] is True and listing["required_when"] == {"mode": ["deep", "abyssal"]}
    assert (listing["mutually_exclusive_with"], listing["notes"], listing["examples"]) == (["$S.height"], "metres", ["3"])
    assert not {"forbidden_when", "co_required_with", "required_one_of", "allowed_bindings", "constraints"} & set(listing)
    assert listed_entry("system/dict", "max", _entry("$S.max", required_one_of=("$S.maxList",)))["required_one_of"] == ["$S.maxList"]


def test_an_absent_selector_is_read_as_the_default_the_catalogue_states():
    entries = [
        _entry("$S.method", value_kind="enum", enum_values=("direct", "iterative"), default="direct"),
        _entry("$S.mode", value_kind="enum", enum_values=("a", "b")),
        _entry("$S.limit", required_when={"method": "direct", "mode": "a"}),
    ]
    assert _violations(entries, {}) == {("limit", "limit is required when method=direct and mode=a.")}
    assert _violations(entries, {"method": "iterative"}) == set()
    assert _violations(entries, {"mode": "b"}) == {("limit", "limit is required when method=direct and mode=a.")}
    assert _violations(entries, {"mode": "b", "limit": 1}) == set()


def test_a_default_outside_the_menu_is_refused():
    import pytest

    with pytest.raises(ValueError, match="not one of its enum_values"):
        _entry("$S.method", value_kind="enum", enum_values=("direct",), default="iterative")


def test_a_default_reaches_a_block_instance_and_the_listing():
    from omnidriver.openfoam.record_key_validation import listed_entry

    entries = [
        _entry("$S.nets.<name>.kind", value_kind="enum", enum_values=("slow", "fast"), default="slow"),
        _entry("$S.nets.<name>.cv", required=True, required_when={"nets.<name>.kind": "slow"}),
    ]
    assert _violations(entries, {"nets.a.other": 1, "nets.b.kind": "fast"}) == {("nets.a.cv", "nets.a.cv is required when nets.<name>.kind=slow.")}
    assert listed_entry("doc", "kind", entries[0])["default"] == "slow"
