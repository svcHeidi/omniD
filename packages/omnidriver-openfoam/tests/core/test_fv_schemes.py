"""``system/fvSchemes``: its catalogued keys, and its values judged through the tables OpenFOAM's source registers."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.openfoam.case_rules import scheme_diagnostics
from omnidriver.openfoam.fv_schemes import (
    FV_SCHEMES_DOCUMENT, FV_SCHEMES_ENTRIES, FV_SCHEMES_ENTRIES_BY_PATH, TABLES, fv_schemes_diagnostics, fv_schemes_document,
    fv_schemes_listing,
)
from omnidriver.openfoam.record_key_validation import make_validator
from omnidriver.openfoam.scheme_tables import committed_menus

_SOURCE = Path(__file__).parent / "fixtures" / "openfoam_v2412_src"

_MENUS = {
    "ddtSchemes": {"Euler", "backward", "bounded"},
    "gradSchemes": {"Gauss", "cellLimited", "leastSquares"},
    "divSchemes": {"Gauss", "bounded"},
    "laplacianSchemes": {"Gauss"},
    "snGradSchemes": {"corrected", "limited", "uncorrected"},
    "interpolationSchemes": {"linear", "limitedLinear", "upwind", "linearUpwind"},
}


def _notes(**values):
    return scheme_diagnostics(
        {table: entries for table, entries in values.items()}, _MENUS, document="system/fvSchemes", source_root="/src",
    )


def test_each_scheme_table_has_a_default_and_a_per_term_entry_whose_menu_is_the_committed_scan():
    assert {entry.driver_path for entry in FV_SCHEMES_ENTRIES} == {
        f"{table}.{key}" for table in TABLES for key in ("default", "<term>")
    }
    for table in TABLES:
        menu = tuple(committed_menus()["tables"][table])
        assert FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.<term>"].enum_values == menu
        assert FV_SCHEMES_ENTRIES_BY_PATH[f"{table}.default"].enum_values == (*menu, "none")


def test_a_value_is_a_phrase_so_an_entry_is_a_string_with_a_menu_not_an_enum():
    assert {entry.value_kind for entry in FV_SCHEMES_ENTRIES} == {"string"}
    assert all(entry.allowed_bindings == {"<term>": None} for entry in FV_SCHEMES_ENTRIES if entry.dynamic_path)


def test_the_document_finds_an_entry_by_table_and_key_and_leaves_any_other_key_open():
    document = fv_schemes_document()
    assert document.open
    entry, binding = document.match(("ddtSchemes", "default"))
    assert (entry.driver_path, binding) == ("ddtSchemes.default", {})
    entry, binding = document.match(("gradSchemes", "grad(T.air)"))
    assert (entry.driver_path, binding) == ("gradSchemes.<term>", {"<term>": "grad(T.air)"})
    assert document.match(("fluxRequired", "default")) is None
    assert document.match(("ddtSchemes", "default", "extra")) is None


def test_a_study_may_set_a_scheme_and_a_misspelling_is_accepted_as_text_for_the_plan_to_note():
    validate = make_validator({FV_SCHEMES_DOCUMENT: fv_schemes_document()}, mapping=lambda: None, owner="test")
    assert validate(FV_SCHEMES_DOCUMENT, ("ddtSchemes", "default"), "backward") == ("string", True)
    assert validate(FV_SCHEMES_DOCUMENT, ("ddtSchemes", "ddt(Vm)"), "backwrd") == ("string", True)
    assert validate(FV_SCHEMES_DOCUMENT, ("fluxRequired", "default"), "no")[1] is False
    with pytest.raises(ValueError):
        validate(FV_SCHEMES_DOCUMENT, ("ddtSchemes", "ddt(Vm); x"), "Euler")
    with pytest.raises(TutorialRecordError):
        validate(FV_SCHEMES_DOCUMENT, ("ddtSchemes", "default"), 3)


def test_the_listing_is_empty_without_the_file_and_shows_menus_with_it(tmp_path):
    assert fv_schemes_listing(tmp_path) == ()
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "fvSchemes").write_text("ddtSchemes { default Euler; }\n")
    listed = {item["driver_path"]: item for item in fv_schemes_listing(tmp_path)}
    assert set(listed) == set(FV_SCHEMES_ENTRIES_BY_PATH)
    assert listed["ddtSchemes.default"]["document"] == FV_SCHEMES_DOCUMENT
    assert "backward" in listed["ddtSchemes.default"]["menu"] and "none" in listed["ddtSchemes.default"]["menu"]


def test_a_composite_value_is_judged_through_the_table_of_each_part():
    assert _notes(laplacianSchemes={"default": ("Gauss", "linear", "corrected")}) == []
    (note,) = _notes(laplacianSchemes={"default": ("Gauss", "lnear", "corrected")})
    assert note.code == "openfoam_scheme_uncatalogued" and note.level == "info"
    assert note.detail["table"] == "interpolationSchemes" and note.detail["value"] == "lnear"
    assert "did you mean 'linear'" in note.message and "limitedLinear" in note.message
    (note,) = _notes(laplacianSchemes={"default": ("Gauss", "linear", "correcetd")})
    assert note.detail["table"] == "snGradSchemes"
    (note,) = _notes(laplacianSchemes={"default": ("Gaus", "linear", "corrected")})
    assert note.detail["table"] == "laplacianSchemes"


def test_the_schemes_a_scheme_reads_are_judged_where_its_constructor_reads_them():
    assert _notes(
        gradSchemes={"default": ("cellLimited", "Gauss", "linear", 1)},
        ddtSchemes={"ddt(Vm)": ("bounded", "Euler")},
        divSchemes={"div(phi,U)": ("Gauss", "linearUpwind", "grad(U)"), "div(U)": ("bounded", "Gauss", "linear")},
        snGradSchemes={"default": ("limited", "corrected", 0.33)},
        laplacianSchemes={"default": ("Gauss", "limitedLinear", 1, "limited", 0.5)},
    ) == []
    assert [n.detail["value"] for n in _notes(ddtSchemes={"ddt(Vm)": ("bounded", "Eulr")})] == ["Eulr"]
    assert [n.detail["table"] for n in _notes(gradSchemes={"default": ("cellLimited", "Gass", "linear", 1)})] == ["gradSchemes"]


def test_a_number_a_dictionary_and_an_explicit_no_default_are_not_judged():
    assert _notes(
        ddtSchemes={"default": "none", "ddt(Vm)": {"ocCoeff": 0.9}},
        snGradSchemes={"default": ("limited", 0.5)},
    ) == []
    assert _notes(ddtSchemes={"ddt(Vm)": "none"}) != []


def _case(tmp_path, ddt="backwrd") -> Path:
    (tmp_path / "system").mkdir(parents=True)
    (tmp_path / "system" / "fvSchemes").write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }\n"
        f"ddtSchemes {{ default none; ddt(Vm) {ddt}; }}\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
    )
    return tmp_path


def test_a_case_whose_source_is_not_supplied_gets_one_note_and_no_judgement(tmp_path):
    (note,) = fv_schemes_diagnostics(_case(tmp_path), env={}, scratch_root=None)
    assert (note.level, note.code) == ("info", "openfoam_source_not_supplied")
    assert "FOAM_SRC" in note.message


def test_a_case_without_fv_schemes_has_nothing_to_say(tmp_path):
    assert fv_schemes_diagnostics(tmp_path, env={}, scratch_root=None) == ()


def test_a_misspelt_scheme_is_noted_with_its_menu_and_a_good_one_is_not(tmp_path):
    env = {"FOAM_SRC": str(_SOURCE)}
    (note,) = fv_schemes_diagnostics(_case(tmp_path / "a"), env=env, scratch_root=tmp_path / "scratch")
    assert note.code == "openfoam_scheme_uncatalogued" and note.field == "ddtSchemes.ddt(Vm)"
    assert "'backwrd'" in note.message and "did you mean 'backward'" in note.message
    assert note.detail["menu"] == ["CrankNicolson", "Euler", "backward", "steadyState"]
    assert fv_schemes_diagnostics(_case(tmp_path / "b", ddt="backward"), env=env, scratch_root=None) == ()


def test_a_supplied_source_that_is_no_directory_is_a_warning(tmp_path):
    (note,) = fv_schemes_diagnostics(_case(tmp_path), env={"FOAM_SRC": str(tmp_path / "missing")}, scratch_root=None)
    assert (note.level, note.code) == ("warning", "openfoam_source_unavailable")
