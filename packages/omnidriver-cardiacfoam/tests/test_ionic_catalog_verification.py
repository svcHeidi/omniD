#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_ionic_catalog_verification
#
# Description
#     Unit tests for the ionic_catalog_verification report parser and
#     diff logic. No OpenFOAM dependency -- exercises parse_report_text /
#     diff_report against hand-written synthetic report text only. The
#     solver-backed check is `omnidriver check --record singleCell`.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Unit tests: report parsing + catalog diffing, no OpenFOAM required.

Constant naming is not a static rule: CellML-generated constants carry ``AC_``,
hand-added ones do not, and one model can mix both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.cardiacfoam.ionic_catalog_verification import (
    ModelVerificationResult,
    VerificationResult,
    catalogue_probe,
    diff_report,
    find_listCellModelsVariables_binary,
    parse_report_text,
    verify_ionic_catalog,
)
from omnidriver.cardiacfoam.ionic_model_catalog import IonicModelEntry


def _entry(*, states=(), algebraic=(), constants=()) -> IonicModelEntry:
    """Synthetic entry, independent of the drift-prone IONIC_MODEL_CATALOG."""
    return IonicModelEntry(
        states=tuple(states),
        algebraic=tuple(algebraic),
        constants=tuple(constants),
        recommended_exports=(),
        compatible_tissues=("myocyte",),
        compatible_solvers=("singleCellSolver",),
        species=("generic",),
        cardiac_region=("ventricle",),
        model_type="ionic",
        description="synthetic test fixture",
    )


def _make_report(*, constants=(), states=(), algebraic=(), ionic_model="Fixture") -> str:
    """Report text in listCellModelsVariables' documented output format."""
    lines = [
        "",
        "========== listCellModelsVariables ==========",
        "",
        "Selected physicsModel: electroModel",
        "Selected myocardiumSolver: singleCellSolver",
        f"Selected ionicModel: {ionic_model}",
        "",
        f"Ionic constants ({len(constants)}) --> initial value",
    ]
    for i, name in enumerate(constants):
        lines.append(f"  constants [{i}] {name} --> 1.0")
    lines += ["", f"Ionic states ({len(states)}) --> initial value"]
    for i, name in enumerate(states):
        lines.append(f"  states [{i}] {name} --> 0.0")
    lines += ["", f"Ionic algebraic ({len(algebraic)})"]
    for i, name in enumerate(algebraic):
        lines.append(f"  algebraic [{i}] {name}")
    lines += ["", "No activeTensionModel configured in electroProperties.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# parse_report_text / diff_report -- pure, no I/O
# ---------------------------------------------------------------------------


def test_report_matching_catalog_is_reported_as_match():
    entry = _entry(constants=("R", "T"), states=("V",), algebraic=("Istim",))
    report = _make_report(constants=["R", "T"], states=["V"], algebraic=["Istim"])
    parsed = parse_report_text(report)

    result = diff_report("Fixture", parsed, entry)

    assert isinstance(result, ModelVerificationResult)
    assert result.status == "match"
    assert result.missing_from_catalog == {}
    assert result.extra_in_catalog == {}


def test_extra_runtime_constant_is_missing_from_catalog():
    entry = _entry(constants=("R", "T"))
    report = _make_report(constants=["R", "T", "F"])
    parsed = parse_report_text(report)

    result = diff_report("Fixture", parsed, entry)

    assert result.status == "mismatch"
    assert result.missing_from_catalog == {"constants": ("F",)}
    assert result.extra_in_catalog == {}


def test_catalog_constant_absent_at_runtime_is_extra_in_catalog():
    entry = _entry(constants=("R", "T", "StaleConstant"))
    report = _make_report(constants=["R", "T"])
    parsed = parse_report_text(report)

    result = diff_report("Fixture", parsed, entry)

    assert result.status == "mismatch"
    assert result.extra_in_catalog == {"constants": ("StaleConstant",)}
    assert result.missing_from_catalog == {}


def test_malformed_report_is_surfaced_as_mismatch_not_silently_ignored():
    entry = _entry(constants=("R", "T"), states=("V",), algebraic=("Istim",))
    garbage = "this is not a listCellModelsVariables report at all\nrandom noise\n"
    parsed = parse_report_text(garbage)

    assert parsed == {"ionic_model": None, "states": [], "algebraic": [], "constants": []}

    result = diff_report("Fixture", parsed, entry)

    assert result.status == "mismatch"
    assert result.extra_in_catalog["constants"] == ("R", "T")
    assert result.extra_in_catalog["states"] == ("V",)
    assert result.extra_in_catalog["algebraic"] == ("Istim",)
    assert result.missing_from_catalog == {}


def test_unprefixed_naming_convention_TNNP_style_matches_cleanly():
    names = ("R", "T", "F", "g_Na", "g_K1")
    entry = _entry(constants=names)
    report = _make_report(constants=list(names))
    parsed = parse_report_text(report)

    result = diff_report("TNNP", parsed, entry)

    assert result.status == "match"


def test_mixed_naming_convention_TWorld_style_matches_cleanly():
    """TWorld mixes AC_ constants with one bare gnalTissueScale, so no static prefix rule holds."""
    names = ("AC_CaMK0", "AC_K_Phos_CaMK", "AC_Whole_cell_PP1", "gnalTissueScale")
    entry = _entry(constants=names)
    report = _make_report(constants=list(names))
    parsed = parse_report_text(report)

    result = diff_report("TWorld", parsed, entry)

    assert result.status == "match"
    bare = [n for n in names if not n.startswith("AC_")]
    assert bare == ["gnalTissueScale"]


def test_diff_report_checks_all_three_fields_independently():
    entry = _entry(constants=("R",), states=("V", "K_i"), algebraic=("Istim",))
    report = _make_report(constants=["R"], states=["V"], algebraic=["Istim", "extraAlg"])
    parsed = parse_report_text(report)

    result = diff_report("Fixture", parsed, entry)

    assert result.status == "mismatch"
    assert result.extra_in_catalog == {"states": ("K_i",)}
    assert result.missing_from_catalog == {"algebraic": ("extraAlg",)}


# ---------------------------------------------------------------------------
# verify_ionic_catalog -- structured, "skipped" is never "verified"
# ---------------------------------------------------------------------------


def test_find_binary_returns_none_or_a_path():
    result = find_listCellModelsVariables_binary()
    assert result is None or isinstance(result, Path)


def test_verify_ionic_catalog_reports_skipped_not_verified_when_utility_absent(monkeypatch):
    import omnidriver.cardiacfoam.ionic_catalog_verification as mod

    monkeypatch.setattr(mod, "find_listCellModelsVariables_binary", lambda *a, **k: None)

    result = verify_ionic_catalog("TNNP")

    assert isinstance(result, VerificationResult)
    assert result.utility_available is False
    assert result.results["TNNP"].status == "skipped"
    assert result.all_match is False


def test_verify_ionic_catalog_all_models_skipped_when_utility_absent(monkeypatch):
    import omnidriver.cardiacfoam.ionic_catalog_verification as mod
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG

    monkeypatch.setattr(mod, "find_listCellModelsVariables_binary", lambda *a, **k: None)

    result = verify_ionic_catalog()

    assert set(result.results) == set(IONIC_MODEL_CATALOG)
    assert all(r.status == "skipped" for r in result.results.values())


def test_the_utility_is_looked_up_and_run_in_the_environment_it_is_given(tmp_path):
    from omnidriver.cardiacfoam.ionic_catalog_verification import find_listCellModelsVariables_binary

    tool = tmp_path / "bin" / "listCellModelsVariables"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    assert find_listCellModelsVariables_binary({"PATH": str(tool.parent)}) == tool
    assert find_listCellModelsVariables_binary({"PATH": str(tmp_path)}) is None


def test_the_probe_fails_naming_the_shell_when_the_utility_is_absent_and_names_the_drift_otherwise(monkeypatch):
    import omnidriver.cardiacfoam.ionic_catalog_verification as mod

    monkeypatch.setattr(mod, "find_listCellModelsVariables_binary", lambda *a, **k: None)
    passed, detail = catalogue_probe({})
    assert not passed and "solver's shell" in detail

    def drifted(model=None, **_):
        return VerificationResult(utility_available=True, results={
            "TNNP": ModelVerificationResult(model="TNNP", status="match"),
            "TWorld": ModelVerificationResult(model="TWorld", status="mismatch", reason="a constant is missing"),
        })

    monkeypatch.setattr(mod, "verify_ionic_catalog", drifted)
    assert catalogue_probe({}) == (
        False, "the catalogue disagrees with the built solver for 1 of 2 models; TWorld: a constant is missing",
    )
    monkeypatch.setattr(mod, "verify_ionic_catalog", lambda **_: VerificationResult(
        utility_available=True, results={"TNNP": ModelVerificationResult(model="TNNP", status="match")},
    ))
    assert catalogue_probe({}) == (True, "1 ionic models match the built solver")


def test_verify_ionic_catalog_rejects_unknown_model():
    with pytest.raises(KeyError):
        verify_ionic_catalog("NotARealIonicModel")


# ---------------------------------------------------------------------------
# The live path's non-solver half -- exercisable without OpenFOAM
# ---------------------------------------------------------------------------


def test_case_synthesis_works_without_the_solver(tmp_path):
    """Exercises the driver-API calls of the live check's OpenFOAM-free half."""
    from omnidriver.cardiacfoam.ionic_catalog_verification import (
        _synthesize_case,
    )
    from omnidriver.cardiacfoam.ionic_model_catalog import (
        IONIC_MODEL_CATALOG,
    )

    entry = IONIC_MODEL_CATALOG["TNNP"]
    case = tmp_path / "case"
    _synthesize_case(case, "TNNP", entry)

    assert (case / "constant" / "electroProperties").is_file()
    assert (case / "constant" / "physicsProperties").is_file()
    # Running blockMesh on this one-cell dict is _verify_one's job, not this half's.
    block_mesh_dict = case / "system" / "blockMeshDict"
    assert block_mesh_dict.is_file()
    assert "hex (0 1 2 3 4 5 6 7) (1 1 1)" in block_mesh_dict.read_text()

    electro = (case / "constant" / "electroProperties").read_text()
    assert "TNNP" in electro
    assert "singleCellSolver" in electro


def test_synthesis_is_attempted_for_every_catalogued_model(tmp_path):
    from omnidriver.cardiacfoam.ionic_catalog_verification import (
        _synthesize_case,
    )
    from omnidriver.cardiacfoam.ionic_model_catalog import (
        IONIC_MODEL_CATALOG,
    )

    failures = {}
    for name, entry in IONIC_MODEL_CATALOG.items():
        try:
            _synthesize_case(tmp_path / name, name, entry)
        except Exception as exc:  # noqa: BLE001 - collected, not swallowed
            failures[name] = str(exc)
    assert failures == {}, f"models the driver cannot configure: {failures}"
