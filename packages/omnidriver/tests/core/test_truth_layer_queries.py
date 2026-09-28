"""The truth layer's two core seams (2026-09-28, roadmap item 4)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.cli import main
from omnidriver.core.plugin_profile import CxxMapping, load_plugin_profile
from omnidriver.core.strict_planning import _catalog_diagnostics

_TOY = "plugins.e2e_record_plugin:E2ERecordPlugin"


def _context(mapping, *, report=None):
    scans = []

    def scan(root, *, allowlist_path, entries):
        scans.append(root)
        return SimpleNamespace(to_json=lambda: report)

    capabilities = SimpleNamespace(
        cxx_mapping=SimpleNamespace(profile=lambda: SimpleNamespace(cxx_mapping=mapping)),
        dict_key_scanner=SimpleNamespace(scan=scan),
        dictionaries=SimpleNamespace(entries=lambda: ()),
    )
    return SimpleNamespace(
        capabilities=capabilities, identity=SimpleNamespace(resolutions={"cxx_mapping": "toy"}),
    ), scans


def _mapping(tmp_path: Path) -> CxxMapping:
    return CxxMapping(
        source_root_variable="TOY_NATIVE_TREE", source_root_relative="src",
        allowlist_path=tmp_path / "allowlist.json",
    )


def test_an_unsupplied_source_root_is_one_info_diagnostic_and_no_scan(tmp_path, monkeypatch):
    monkeypatch.delenv("TOY_NATIVE_TREE", raising=False)
    context, scans = _context(_mapping(tmp_path))
    (diagnostic,) = _catalog_diagnostics(context)
    assert (diagnostic.level, diagnostic.code) == ("info", "plugin_cxx_source_not_supplied")
    assert "TOY_NATIVE_TREE" in diagnostic.message
    assert scans == []


def test_a_supplied_root_that_is_not_a_directory_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("TOY_NATIVE_TREE", str(tmp_path / "absent"))
    context, scans = _context(_mapping(tmp_path))
    (diagnostic,) = _catalog_diagnostics(context)
    assert (diagnostic.level, diagnostic.code) == ("error", "plugin_cxx_source_unavailable")
    assert scans == []


def test_a_supplied_root_is_scanned_and_every_drift_list_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "tree" / "src").mkdir(parents=True)
    monkeypatch.setenv("TOY_NATIVE_TREE", str(tmp_path / "tree"))
    report = {"status": "failed", "stale_paths": ["a.b"], "any_new_kind": ["x"], "values": {"a": ["b"]}}
    context, scans = _context(_mapping(tmp_path), report=report)
    diagnostics = _catalog_diagnostics(context)
    assert scans == [(tmp_path / "tree" / "src").resolve()]
    assert {(d.level, d.code) for d in diagnostics} == {
        ("error", "plugin_dict_key_stale_paths"), ("error", "plugin_dict_key_any_new_kind"),
    }


def test_the_profile_names_a_variable_and_a_relation_never_a_path(tmp_path):
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\nplugin: {id: toy, api_version: '2'}\n"
        "cxx_mapping:\n  source_root: {variable: TOY_NATIVE_TREE, relative: ../src}\n"
        "  reviewed_allowlist: allowlist.json\n"
    )
    mapping = load_plugin_profile(profile).cxx_mapping
    assert mapping.source_root({}) is None
    assert mapping.source_root({"TOY_NATIVE_TREE": str(tmp_path / "tutorials")}) == tmp_path / "src"
    profile.write_text(profile.read_text().replace(
        "  source_root: {variable: TOY_NATIVE_TREE, relative: ../src}\n", "  source_roots: [../src]\n",
    ))
    with pytest.raises(ValueError, match="cxx_mapping.source_root"):
        load_plugin_profile(profile)


def _toy_cases(tmp_path: Path) -> Path:
    (tmp_path / "native" / "toyTutorial" / "constant").mkdir(parents=True)
    (tmp_path / "native" / "toyTutorial" / "constant" / "mesh.json").write_text('{"cells": "1"}')
    return tmp_path / "native"


@pytest.mark.parametrize("filters, found", [
    ((), 1),
    (("--document", "constant/mesh.json"), 1),
    (("--key", "cells"), 1),
    (("--document", "constant/other.json"), 0),
    (("--key", "faces"), 0),
])
def test_catalog_lists_the_record_key_catalogue(tmp_path, capsys, filters, found):
    exit_code = main([
        "catalog", "--plugin", _TOY, "--entry", "toyTutorial",
        "--cases-root", str(_toy_cases(tmp_path)), *filters,
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(payload["entries"]) == found
    assert payload["cxx_source"] is None      # the toy declares no C++ mapping
    if found:
        assert payload["entries"][0]["value_kind"] == "integer"


def test_catalog_refuses_an_entry_that_is_not_a_record_as_json(tmp_path, capsys):
    exit_code = main([
        "catalog", "--plugin", _TOY, "--entry", "noSuchRecord", "--cases-root", str(tmp_path),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1 and payload["status"] == "failed"


def test_document_and_key_belong_to_catalog_only(tmp_path):
    with pytest.raises(SystemExit):
        main(["describe", "--plugin", _TOY, "--entry", "toyTutorial", "--key", "cells"])
