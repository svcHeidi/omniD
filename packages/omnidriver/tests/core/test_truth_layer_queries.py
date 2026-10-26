"""The truth layer's two core seams."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core import catalog_query
from omnidriver.core.tutorial_records import TutorialRecordError

from cli_refusal import refusal
from omnidriver.core.plugin_profile import load_plugin_profile

_TOY = "plugins.toy:ToyStack"


def test_the_profile_names_a_variable_and_a_relation_never_a_path(tmp_path):
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\nplugin: {id: toy, api_version: '3'}\n"
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


def test_document_and_key_belong_to_catalog_only(tmp_path, capsys):
    assert "only valid with action=catalog" in refusal(
        capsys, ["describe", "--plugin", _TOY, "--entry", "toyTutorial", "--key", "cells"],
    )


def test_catalog_uncatalogued_and_scan_refuse_a_stack_with_no_cxx_by_name(tmp_path, capsys):
    assert "declares no C++ source" in refusal(capsys, ["catalog", "--plugin", _TOY, "--uncatalogued"])
    assert main(["scan", "--plugin", _TOY, "--scratch-dir", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "the stack declares no C++ source"


def test_uncatalogued_takes_no_entry_and_scan_needs_a_scratch_root(tmp_path, capsys, monkeypatch):
    assert "take no --entry" in refusal(capsys, ["catalog", "--plugin", _TOY, "--uncatalogued", "--entry", "toyTutorial"])
    monkeypatch.delenv("OMNIDRIVER_SCRATCH_DIR", raising=False)
    assert main(["scan", "--plugin", _TOY]) == 1
    assert "scratch root" in json.loads(capsys.readouterr().out)["error"]


def test_catalog_unread_refuses_a_stack_with_no_cxx_and_is_exclusive_of_uncatalogued(tmp_path, capsys):
    assert "declares no C++ source" in refusal(capsys, ["catalog", "--plugin", _TOY, "--unread"])
    assert "pass one" in refusal(capsys, ["catalog", "--plugin", _TOY, "--unread", "--uncatalogued"])


@pytest.mark.parametrize("unread", [False, True])
def test_a_scan_that_was_not_run_is_refused_by_name_never_an_empty_list(monkeypatch, unread):
    from omnidriver.core.plugin_interface import load_plugin_context

    monkeypatch.setattr(catalog_query, "cxx_evidence", lambda *a, **k: {
        "variable": "TOY_NATIVE_TREE", "relative": "../src", "root": None,
        "scanned": False, "reason": "source root not supplied",
    })
    with pytest.raises(TutorialRecordError, match="nothing was scanned.*source root not supplied.*TOY_NATIVE_TREE"):
        catalog_query.scan_query(load_plugin_context(_TOY), cache_root=None, unread=unread)


def test_the_scanner_is_given_the_scanned_roots_place_in_the_supplied_repository(tmp_path):
    from types import SimpleNamespace

    from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
    from omnidriver.core.plugin_profile import CxxMapping
    from omnidriver.core.provider_stack import ProviderStack
    from omnidriver.core.repository import Repository

    (tmp_path / "src").mkdir()
    (tmp_path / "tutorials").mkdir()
    given = {}

    def scanner(root, **kwargs):
        given.update(kwargs)
        return SimpleNamespace(to_json=lambda: {})

    mapping = CxxMapping(
        source_root_variable="TOY_NATIVE_TREE", source_root_relative="../src", allowlist_path=tmp_path / "a.json",
    )
    provider = SimpleNamespace(
        plugin_id="toy", plugin_api_version="3",
        get_profile=lambda: SimpleNamespace(cxx_mapping=mapping, case_files=(), requires=()),
        get_dict_key_scanner=lambda: scanner, get_dictionary_catalog=lambda: DictionaryCatalog({}),
    )
    repository = Repository(
        root=tmp_path, plugin="toy", tutorials=tmp_path / "tutorials", source=tmp_path / "src",
        scripts=tmp_path / "scripts",
    )
    context = SimpleNamespace(stack=ProviderStack((provider,)), repository=repository)
    catalog_query.cxx_evidence(context, {"TOY_NATIVE_TREE": str(tmp_path / "tutorials")})
    assert str(given["source_prefix"]) == "src"
