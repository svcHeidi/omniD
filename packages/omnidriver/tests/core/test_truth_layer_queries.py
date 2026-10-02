"""The truth layer's two core seams (2026-09-28, roadmap item 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.plugin_profile import load_plugin_profile

_TOY = "plugins.e2e_record_plugin:E2ERecordPlugin"


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


def test_catalog_uncatalogued_and_scan_answer_for_the_whole_stack(tmp_path, capsys):
    assert main(["catalog", "--plugin", _TOY, "--uncatalogued"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert (payload["cxx_source"], payload["uncatalogued"]) == (None, [])
    assert main(["scan", "--plugin", _TOY, "--scratch-dir", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "the stack declares no C++ source"


def test_uncatalogued_takes_no_entry_and_scan_needs_a_scratch_root(tmp_path, capsys, monkeypatch):
    with pytest.raises(SystemExit):
        main(["catalog", "--plugin", _TOY, "--uncatalogued", "--entry", "toyTutorial"])
    monkeypatch.delenv("OMNIDRIVER_SCRATCH_DIR", raising=False)
    assert main(["scan", "--plugin", _TOY]) == 1
    assert "scratch root" in json.loads(capsys.readouterr().out)["error"]
