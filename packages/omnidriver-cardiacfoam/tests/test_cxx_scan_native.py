"""The C++ scan on the supplied native cardiacFOAM tree: the catalogue
agrees with it, and a key or a model added to the C++ is accepted, reported
``uncatalogued`` and settable in a case that does not yet hold it, with no
test or catalogue edit."""
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
_SELECTORS = "// * * * * * * * * * * * * * * * * Selectors"


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
    assert report.contradictions == [], "\n".join(report.contradictions)
    assert report.selector_values["$ELECTRO_MODEL_COEFFS.ionicModel"]


def test_the_scan_reads_types_defaults_scopes_and_selections():
    scan = scan_source(_source_root())
    model = next(r for r in scan.reads if r.key == "ionicModel" and r.function == "Foam::ionicModel::New")
    assert (model.method, model.type, model.default, model.scope) == ("lookup", "word", None, ())
    c0 = next(r for r in scan.reads if r.key == "c0")
    assert (c0.method, c0.type) == ("dimensioned", "dimensionedScalar")
    assert any(r.selected_as for r in scan.reads if r.function and "TNNP::" in r.function)
    assert scan.resolution()["resolved_scope"] > 50


_COEFFS = "constant/electroProperties:singleCellSolverCoeffs."
#: One read of each shape, none of them in the native case: a typed get, a
#: read with a default, a key in a new sub-dictionary, and a key read through
#: a helper the selector passes its dictionary to.
_ADDED_READS = (
    '    const label omniLabel(dict.get<label>("omniLabel"));\n'
    '    const scalar omniDefaulted(dict.lookupOrDefault<scalar>("omniDefaulted", 2.0));\n'
    '    const scalar omniDeep(dict.subDict("omniBlock").lookupOrDefault<scalar>("omniDeep", 1.0));\n'
    '    const scalar omniPassed(omniHelper(dict));\n'
)
_HELPER = (
    "namespace Foam {\n"
    "static scalar omniHelper(const dictionary& d)\n"
    "{\n    return d.lookupOrDefault<scalar>(\"omniThroughHelper\", 3.0);\n}\n}\n\n"
)
_STUDY = {
    _COEFFS + "omniLabel": 3,
    _COEFFS + "omniDefaulted": 2.5,
    _COEFFS + "omniBlock.omniDeep": 4.0,
    _COEFFS + "omniThroughHelper": 7.0,
}


def _tree_with_new_reads(tmp_path: Path, *, reads: bool = True, model: bool = False) -> Path:
    """A scratch copy of the native ``src/`` and the singleCell case, with
    reads of new keys added to ``ionicModel::New`` and, optionally, a new
    ionic model registered (a copy of AlievPanfilov). The case is left as
    the native tree has it."""
    native = native_tutorials_root()
    tree = tmp_path / "tree"
    shutil.copytree(_source_root(), tree / "src")
    shutil.copytree(native / _SINGLE_CELL, tree / "tutorials" / _SINGLE_CELL)
    reader = tree / "src" / "ionicModels" / "ionicModel" / "ionicModel.C"
    text = reader.read_text()
    assert _ANCHOR in text and _SELECTORS in text, "the native ionicModel.C changed; pick other anchors"
    if reads:
        reader.write_text(text.replace(_ANCHOR, _ANCHOR + _ADDED_READS).replace(_SELECTORS, _HELPER + _SELECTORS, 1))
    if model:
        source = tree / "src" / "ionicModels" / "AlievPanfilov"
        target = tree / "src" / "ionicModels" / "OmniProbe"
        target.mkdir()
        for path in source.iterdir():
            (target / path.name.replace("AlievPanfilov", "OmniProbe")).write_text(
                path.read_text().replace("AlievPanfilov", "OmniProbe")
            )
    return tree


def _plan(tree: Path, tmp_path: Path, study: dict):
    return strict_plan(
        "singleCell", overrides={"cases_root": str(tree / "tutorials"), **study},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


def _staged(tmp_path: Path) -> str:
    return " ".join((tmp_path / "scratch" / "records" / "singleCell" / "constant" / "electroProperties").read_text().split())


def test_keys_added_to_the_cxx_plan_are_uncatalogued_and_settable(tmp_path, monkeypatch):
    tree = _tree_with_new_reads(tmp_path)
    case = (tree / "tutorials" / _SINGLE_CELL / "constant" / "electroProperties").read_text()
    assert not any(key.rsplit(".", 1)[-1] in case for key in _STUDY)
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    report = _plan(tree, tmp_path, _STUDY).to_json()
    assert report["status"] == "ok", json.dumps(report["catalog_coverage_errors"], indent=1)
    notes = " ".join(d["message"] for d in report["catalog_coverage_errors"] if d["code"] == "plugin_catalog_uncatalogued")
    staged = _staged(tmp_path)
    for name, value in _STUDY.items():
        leaf = name.rsplit(".", 1)[-1]
        assert f'"key": "{leaf}"' in notes
        assert f"{leaf} {value};" in staged
    assert "omniBlock { omniDeep 4.0; }" in staged
    assert list((tmp_path / "scratch" / "cxx-scan").glob("*.json"))


def test_a_new_key_is_refused_at_a_path_the_cxx_does_not_read_or_with_the_wrong_type(tmp_path, monkeypatch):
    tree = _tree_with_new_reads(tmp_path)
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    with pytest.raises((TutorialRecordError, KeyError), match=r"reads 'omniThroughHelper' at .*not at"):
        _plan(tree, tmp_path, {_COEFFS + "outputVariables.omniThroughHelper": 7.0})
    with pytest.raises((TutorialRecordError, KeyError), match="omniLabel"):
        _plan(tree, tmp_path, {"constant/electroProperties:omniLabel": 3})
    with pytest.raises((TutorialRecordError, ValueError), match="as label"):
        _plan(tree, tmp_path, {_COEFFS + "omniLabel": 3.5})
    with pytest.raises((TutorialRecordError, KeyError), match="TaScale' only through dictionaries the scan cannot place"):
        _plan(tree, tmp_path, {_COEFFS + "TaScale": 2.0})


def test_without_the_cxx_read_the_same_study_is_refused(tmp_path, monkeypatch):
    tree = _tree_with_new_reads(tmp_path, reads=False)
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    with pytest.raises((TutorialRecordError, KeyError), match="reads no key named 'omniLabel'"):
        _plan(tree, tmp_path, {_COEFFS + "omniLabel": 3})


def test_a_model_a_scanned_selection_table_registers_plans_uncatalogued(tmp_path, monkeypatch):
    tree = _tree_with_new_reads(tmp_path, reads=False, model=True)
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tree / "tutorials"))
    report = _plan(tree, tmp_path, {_COEFFS + "ionicModel": "OmniProbe"}).to_json()
    assert report["status"] == "ok", json.dumps(report["validation_diagnostics"], indent=1)
    assert any('"value": "OmniProbe"' in d["message"] for d in report["catalog_coverage_errors"])
    assert "ionicModel OmniProbe;" in _staged(tmp_path)
