"""``rtst_scanner.runtime_selection_report``: catalogue enums vs C++
runtime-selection tables. The real tree is covered by cardiacfoam's native
``test_rtst_enum_contract.py``; this pins the comparison rules on fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.dict_keys_scanner import strict_dict_key_report
from omnidriver.openfoam.rtst_scanner import runtime_selection_report


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "models").mkdir(parents=True, exist_ok=True)
    (src / "models" / "fast.H").write_text('class fastModel : public model { OverrideTypeName("fast"); };\n')
    (src / "models" / "fast.C").write_text("addToRunTimeSelectionTable(model, fastModel, dictionary);\n")
    (src / "models" / "slow.C").write_text(
        'void f(const dictionary& d) { d.lookup("model"); }\n'
        "addToRunTimeSelectionTable(model, slow, dictionary);\n"
        "// addToRunTimeSelectionTable(model, commented, dictionary);\n"
    )
    return src


def _enum(path: str, values: tuple[str, ...]) -> DictEntry:
    return DictEntry(driver_path=path, description="", value_kind="enum", enum_values=values)


def _mapping(mode: str = "strict") -> dict:
    return {"by_path": {"model": {"base": "model", "mode": mode}}, "not_runtime_selected": {}, "internal_bases": {}}


def test_agreeing_values_report_no_drift_and_show_the_registered_names(tmp_path):
    report = runtime_selection_report(
        _src(tmp_path), entries=(_enum("model", ("fast", "slow")),), mapping=_mapping(),
    )
    assert report["selector_values"] == {"model": ["fast", "slow"]}
    assert not any(report[key] for key in (
        "selector_drift", "unclassified_selector_enums", "unmapped_selector_bases", "unused_selector_mapping",
    ))


def test_each_mode_names_the_side_that_differs(tmp_path):
    src = _src(tmp_path)
    entries = (_enum("model", ("fast", "gone")),)
    assert runtime_selection_report(src, entries=entries, mapping=_mapping("strict"))["selector_drift"] == [
        "model (strict, model): catalogue only ['gone']; C++ only ['slow']",
    ]
    assert runtime_selection_report(src, entries=entries, mapping=_mapping("subset"))["selector_drift"]
    assert runtime_selection_report(
        src, entries=(_enum("model", ("fast", "slow", "extra")),), mapping=_mapping("polymorphic"),
    )["selector_drift"] == []


def test_unmapped_unclassified_and_unused_are_each_drift(tmp_path):
    report = runtime_selection_report(
        _src(tmp_path),
        entries=(_enum("other", ("a",)),),
        mapping={
            "by_path": {"gone.path": {"base": "model", "mode": "strict"}},
            "not_runtime_selected": {"gone.word": "why"},
            "internal_bases": {"noSuchBase": "why", "model": "why"},
        },
    )
    assert report["unclassified_selector_enums"] == ["other"]
    assert report["unused_selector_mapping"] == [
        "by_path:gone.path", "not_runtime_selected:gone.word",
        "internal_bases:model", "internal_bases:noSuchBase",
    ]
    unmapped = runtime_selection_report(
        _src(tmp_path), entries=(), mapping={"by_path": {}, "not_runtime_selected": {}, "internal_bases": {}},
    )["unmapped_selector_bases"]
    assert unmapped == ["model"]


def test_the_strict_report_fails_on_selector_drift_only_when_mapped(tmp_path):
    src = _src(tmp_path)
    entries = (_enum("model", ("fast",)),)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({}))
    assert "selector_drift" not in strict_dict_key_report(src, allowlist_path=allowlist, entries=entries).to_json()
    allowlist.write_text(json.dumps({"runtime_selection": _mapping()}))
    report = strict_dict_key_report(src, allowlist_path=allowlist, entries=entries)
    assert report.status == "failed"
    assert report.to_json()["selector_drift"]
