"""``CardiacFoamPlugin.get_record_key_catalog`` over a native case committed verbatim as a fixture
(``restitutionCurves_s1s2Protocol``): it lists what ``record_key_validator`` accepts and nothing it
refuses; both are the same three rules (``record_key_validation``)."""
from __future__ import annotations

from pathlib import Path

from foamlib import FoamFile

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.record_key_validation import record_key_validator
from omnidriver.core.runtime.record_surface import ANY_KEY

CASE = Path(__file__).resolve().parent / "fixtures" / "tutorials" / "electrophysiologyProtocols" / "restitutionCurves_s1s2Protocol"


def _catalogue():
    return CardiacFoamPlugin().get_record_key_catalog(CASE)


def test_the_coeffs_token_is_the_cases_own_solver_scope():
    keys = {(e["document"], e["key"]) for e in _catalogue()}
    assert not [k for k in keys if "$" in k[1]]
    assert ("constant/electroProperties", "singleCellSolverCoeffs.tissue") in keys
    assert ("constant/electroProperties", "myocardiumSolver") in keys
    assert ("constant/physicsProperties", "type") in keys
    assert not [k for k in keys if k[1].startswith(("monodomainSolverCoeffs.", "bidomainSolverCoeffs."))]


def test_every_system_document_of_the_case_is_listed_open_and_nothing_else_is():
    open_entries = [e for e in _catalogue() if e["key"] == ANY_KEY]
    assert sorted(e["document"] for e in open_entries) == sorted(
        p.relative_to(CASE).as_posix() for p in (CASE / "system").rglob("*") if p.is_file()
    )
    assert all(e["validated"] is False and "value_kind" not in e for e in open_entries)


def test_every_listed_key_the_case_holds_is_accepted_by_the_validator_with_its_kind():
    """Values are read typed with foamlib: the stack's config reader answers text, which the shape check is not for."""
    checked = []
    for entry in _catalogue():
        if entry["key"] == ANY_KEY or "<" in entry["key"] or "[Int]" in entry["key"]:
            continue
        key_path = tuple(entry["key"].split("."))
        try:
            value = FoamFile(CASE / entry["document"])[key_path]
        except KeyError:
            continue
        assert record_key_validator(entry["document"], key_path, value) == (entry["value_kind"], True), entry
        checked.append(entry["key"])
    assert "singleCellSolverCoeffs.tissue" in checked and "myocardiumSolver" in checked


def test_describe_lists_only_the_keys_the_cases_own_solver_allows():
    plugin = CardiacFoamPlugin()
    listed = plugin.get_record_key_catalog(CASE)
    narrowed = plugin.select_applicable_record_keys(listed, CASE)
    kept = {(e["document"], e["key"]) for e in narrowed}
    gone = {(e["document"], e["key"]) for e in listed} - kept
    assert gone, "a single-cell case rules out the keys of the other solvers"
    # What a study can make apply by setting another key (here the ionic model) stays listed.
    assert ("constant/electroProperties", "singleCellSolverCoeffs.tissue") in kept
    by_key = {(e["document"], e["key"]): e for e in listed}
    for item in (by_key[key] for key in gone):
        assert (
            "singleCellSolver" not in item.get("applicable_when", {}).get("myocardiumSolver", ["singleCellSolver"])
            or item.get("forbidden_when", {}).get("myocardiumSolver")
        ), item["key"]
    assert any(e.get("applicable_when", {}).get("ionicModel") for e in narrowed)
    assert [e for e in listed if e["document"] != "constant/electroProperties"] == [
        e for e in narrowed if e["document"] != "constant/electroProperties"
    ]


def test_a_case_with_no_electro_properties_is_listed_whole(tmp_path):
    plugin = CardiacFoamPlugin()
    keys = ({"document": "system/controlDict", "key": "<any>", "validated": False},)
    assert plugin.select_applicable_record_keys(keys, tmp_path) == keys
