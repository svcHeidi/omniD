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


def test_the_catalogued_control_dict_keys_are_listed_with_their_bounds_beside_the_open_row():
    control = [e for e in _catalogue() if e["document"] == "system/controlDict"]
    delta_t = next(e for e in control if e["key"] == "deltaT")
    assert delta_t["exclusive_minimum"] == 0 and delta_t["value_kind"] == "scalar"
    assert next(e for e in control if e["key"] == "endTime")["minimum"] == 0
    assert [e for e in control if e["key"] == ANY_KEY] == [{"document": "system/controlDict", "key": ANY_KEY, "validated": False}]


def test_a_pre_pacing_file_the_case_holds_is_listed_by_the_keys_a_study_may_set(tmp_path):
    import shutil

    case = tmp_path / "case"
    shutil.copytree(CASE, case)
    (case / "constant" / "prePacingProperties").write_text("FoamFile { version 2.0; format ascii; class dictionary; object x; }\n")
    keys = {e["key"] for e in CardiacFoamPlugin().get_record_key_catalog(case) if e["document"] == "constant/prePacingProperties"}
    assert {"tolerance", "maxBeats", "regions.<region_name>.maxBeats", "singleCellStimulus.stim_start", "regions.<region_name>.singleCellStimulus.stim_start"} <= keys
    assert not [key for key in keys if "$" in key]
