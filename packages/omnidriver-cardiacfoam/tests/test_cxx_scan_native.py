"""The C++ scan on the supplied native cardiacFOAM tree: the catalogue
agrees with it, and a key added to the C++ is accepted, reported
``uncatalogued`` and settable, with no test or catalogue edit."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from cardiacfoam_native import native_tutorials_root
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.openfoam.dict_keys_scanner import catalog_report, scan_source

pytestmark = pytest.mark.native

_MAPPING = CardiacFoamPlugin.get_profile().cxx_mapping
_SINGLE_CELL = "electrophysiologyProtocols/singleCell"
_ANCHOR = '    const word modelType(dict.lookup("ionicModel"));\n'
_ADDED_READ = '    const scalar omnidriverProbe(dict.lookupOrDefault<scalar>("omnidriverProbe", 1.0));\n'
_STUDY_KEY = "constant/electroProperties:singleCellSolverCoeffs.omnidriverProbe"


def _source_root() -> Path:
    native_tutorials_root()
    return _MAPPING.source_root(os.environ)


def _report():
    context = load_plugin_context("cardiacfoam")
    return catalog_report(
        _source_root(), allowlist_path=_MAPPING.allowlist_path,
        entries=context.capabilities.dictionaries.entries(),
    )


def test_the_catalogue_agrees_with_the_cxx():
    report = _report()
    assert report.contradictions == (), "\n".join(report.contradictions)
    assert report.selector_values["$ELECTRO_MODEL_COEFFS.ionicModel"]


def test_the_scan_reads_types_defaults_scopes_and_selections():
    scan = scan_source(_source_root())
    model = next(r for r in scan.reads if r.key == "ionicModel" and r.function == "Foam::ionicModel::New")
    assert (model.method, model.type, model.required, model.scope) == ("lookup", "word", True, ())
    c0 = next(r for r in scan.reads if r.key == "c0")
    assert (c0.method, c0.type) == ("dimensioned", "dimensionedScalar")
    assert any(r.selected_as for r in scan.reads if r.function and "TNNP::" in r.function)
    assert scan.resolution()["resolved_scope"] > 50


def _tree_with_a_new_key(tmp_path: Path) -> Path:
    """A scratch copy of the native ``src/`` and the singleCell case, with
    one key read added to the C++ and set in the case."""
    native = native_tutorials_root()
    tree = tmp_path / "tree"
    shutil.copytree(_source_root(), tree / "src")
    shutil.copytree(native / _SINGLE_CELL, tree / "tutorials" / _SINGLE_CELL)
    reader = tree / "src" / "ionicModels" / "ionicModel" / "ionicModel.C"
    text = reader.read_text()
    assert _ANCHOR in text, "the native ionicModel::New changed; pick another anchor"
    reader.write_text(text.replace(_ANCHOR, _ANCHOR + _ADDED_READ))
    properties = tree / "tutorials" / _SINGLE_CELL / "constant" / "electroProperties"
    text = properties.read_text()
    assert "    ionicModel    TWorld;\n" in text
    properties.write_text(text.replace("    ionicModel    TWorld;\n", "    ionicModel    TWorld;\n    omnidriverProbe 1.0;\n", 1))
    return tree


def _plan(tree: Path, tmp_path: Path, study: dict):
    return strict_plan(
        "singleCell", overrides={"cases_root": str(tree / "tutorials"), **study},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


def test_a_key_added_to_the_cxx_plans_is_uncatalogued_and_settable(tmp_path, monkeypatch):
    tree = _tree_with_a_new_key(tmp_path)
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    report = _plan(tree, tmp_path, {_STUDY_KEY: 2.5}).to_json()
    assert report["status"] == "ok", json.dumps(report["catalog_coverage_errors"], indent=1)
    notes = [d["message"] for d in report["catalog_coverage_errors"] if d["code"] == "plugin_catalog_uncatalogued"]
    assert any('"key": "omnidriverProbe"' in note and '"default": "1.0"' in note for note in notes)
    staged = (tmp_path / "scratch" / "records" / "singleCell" / "constant" / "electroProperties").read_text()
    assert "omnidriverProbe 2.5;" in " ".join(staged.split())
    assert list((tmp_path / "scratch" / "cxx-scan").glob("*.json"))
    with pytest.raises((TutorialRecordError, ValueError), match="omnidriverProbe"):
        _plan(tree, tmp_path, {_STUDY_KEY: "high"})


def test_without_the_cxx_read_the_same_study_is_refused(tmp_path, monkeypatch):
    tree = _tree_with_a_new_key(tmp_path)
    reader = tree / "src" / "ionicModels" / "ionicModel" / "ionicModel.C"
    reader.write_text(reader.read_text().replace(_ADDED_READ, ""))
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    with pytest.raises((TutorialRecordError, KeyError), match="omnidriverProbe"):
        _plan(tree, tmp_path, {_STUDY_KEY: 2.5})
