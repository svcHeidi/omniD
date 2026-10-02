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


def test_a_switch_is_compared_by_meaning_not_spelling():
    entries = [_entry("$S.scale", required=True, applicable_when={"enabled": "true"})]
    assert _violations(entries, {"enabled": True}) == {("scale", "scale is required.")}
    assert _violations(entries, {"enabled": False}) == set()


def test_each_instance_of_a_block_is_judged_on_its_own_values():
    entries = [
        _entry("$S.nets.<name>.kind", dynamic_path=True),
        _entry("$S.nets.<name>.cv", dynamic_path=True, required=True, applicable_when={"nets.<name>.kind": "fast"}),
    ]
    context = {"nets.a.kind": "fast", "nets.b.kind": "slow", "nets.c.kind": "fast", "nets.c.cv": 4.0}
    assert _violations(entries, context) == {("nets.a.cv", "nets.a.cv is required.")}


def test_a_literal_the_catalogue_uses_beside_a_block_is_not_an_instance():
    entries = [
        _entry("$S.ecg.<name>.solver", dynamic_path=True, required=True),
        _entry("$S.ecg.electrodes.<electrode>", dynamic_path=True),
    ]
    assert _violations(entries, {"ecg.electrodes.V1": "(0 0 0)", "ecg.main.other": 1}) == {
        ("ecg.main.solver", "ecg.main.solver is required."),
    }


def test_an_unlisted_value_is_never_judged():
    """Menus belong to the C++; a name the catalogue lacks passes every relation."""
    entries = [_entry("$S.model", value_kind="enum", enum_values=("a",)), _entry("$S.x", required=True, applicable_when={"model": "a"})]
    assert _violations(entries, {"model": "scannedNewModel"}) == set()


def test_leaves_are_read_through_blocks(tmp_path):
    path = tmp_path / "dict"
    path.write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; object dict; }\n"
        "top 1;\nblock { inner { leaf yes; } other word; }\n"
    )
    assert read_leaves(path) == {"top": 1, "block.inner.leaf": True, "block.other": "word"}
    assert read_leaves(path, ("block",)) == {"inner.leaf": True, "other": "word"}
    assert flatten({"a": {"b": 1}, None: 2}) == {"a.b": 1}
