"""Warn-level sweep of a case dictionary's keys against the plugin catalogue
-- the direction the C++ scanner cannot see, since a key nobody catalogued
is silently ignored by OpenFOAM rather than appearing anywhere in C++."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.case_dict_keys import case_dict_key_diagnostics

_HEADER = """\
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      electroProperties;
}
"""


def _write(case_root: Path, body: str) -> None:
    d = case_root / "constant"
    d.mkdir(parents=True, exist_ok=True)
    (d / "electroProperties").write_text(_HEADER + body)


@pytest.mark.parametrize("error", [ValueError("invalid dictionary"), OSError("read denied")])
def test_inspection_failure_reports_reason(tmp_path, monkeypatch, error):
    _write(tmp_path, "known 1;")

    def fail(path):
        raise error

    monkeypatch.setattr("foamlib.FoamFile", fail)
    diags = case_dict_key_diagnostics(
        tmp_path, catalogued_paths=("known",),
        dict_relpaths=("constant/electroProperties",),
    )
    assert len(diags) == 1
    assert diags[0].level == "warning"
    assert diags[0].code == "case_dict_inspection_unavailable"
    assert diags[0].source == "constant/electroProperties"
    assert str(error) in diags[0].message


def test_node_read_failure_discards_partial_key_warnings(tmp_path, monkeypatch):
    _write(tmp_path, "known 1;")

    class UnreadableNode(dict):
        def __getitem__(self, key):
            raise OSError("node read failed")

    monkeypatch.setattr(
        "foamlib.FoamFile",
        lambda path: {"typo": 1, "known": UnreadableNode(leaf=2)},
    )
    diags = case_dict_key_diagnostics(
        tmp_path, catalogued_paths=("known.leaf",),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.code for d in diags] == ["case_dict_inspection_unavailable"]
    assert "node read failed" in diags[0].message


def test_a_missing_file_is_silent(tmp_path, monkeypatch):
    def unexpected_read(path):
        pytest.fail("a missing dictionary must not be read")

    monkeypatch.setattr("foamlib.FoamFile", unexpected_read)
    assert case_dict_key_diagnostics(
        tmp_path, catalogued_paths=(),
        dict_relpaths=("constant/electroProperties",),
    ) == ()


def test_misspelled_key_is_reported(tmp_path):
    _write(tmp_path, """
myocardiumSolver singleCellSolver;
singleCellSolverCoeffs
{
    ionicModel      TWorld;
    activeTensionModl LandNiederer;
}
""")
    diags = case_dict_key_diagnostics(
        tmp_path,
        # Scope-relative: _parse_path strips the "$ELECTRO_MODEL_COEFFS." prefix.
        catalogued_paths=("myocardiumSolver", "ionicModel", "activeTensionModel"),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.field for d in diags] == ["activeTensionModl"]
    assert diags[0].level == "warning"
    assert diags[0].code == "uncatalogued_case_dict_key"


def test_runtime_selection_coeffs_dict_is_not_reported(tmp_path):
    # <model>Coeffs is OpenFOAM's runtime-selection convention, not a plugin
    # key, so warning about it would fire on every case.
    _write(tmp_path, """
myocardiumSolver singleCellSolver;
singleCellSolverCoeffs
{
    ionicModel TWorld;
}
""")
    diags = case_dict_key_diagnostics(
        tmp_path,
        catalogued_paths=("myocardiumSolver", "ionicModel"),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.field for d in diags] == []


def test_a_misspelled_coeffs_dict_is_still_reported(tmp_path):
    _write(tmp_path, """
myocardiumSolver singleCellSolver;
singleCellSolverCoefs
{
    ionicModel TWorld;
}
""")
    diags = case_dict_key_diagnostics(
        tmp_path,
        catalogued_paths=("myocardiumSolver", "ionicModel"),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.field for d in diags] == ["singleCellSolverCoefs"]


# ---------------------------------------------------------------------------
# Position-aware matching: a <placeholder> segment matches any instance name
# ---------------------------------------------------------------------------


def test_user_chosen_instance_name_under_a_wildcard_is_not_reported(tmp_path):
    # "ECG" is the author's own instance label, matched by position (it sits
    # where the catalogue's <name> placeholder expects it), not by name.
    _write(tmp_path, """
ecgDomains
{
    ECG
    {
        sigmaExtracellular 0.2;
    }
}
""")
    diags = case_dict_key_diagnostics(
        tmp_path,
        catalogued_paths=("ecgDomains.<name>.sigmaExtracellular",),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.field for d in diags] == []


def test_a_typo_beneath_a_wildcard_is_still_reported(tmp_path):
    _write(tmp_path, """
ecgDomains
{
    ECG
    {
        sigmaExtracellulr 0.2;
    }
}
""")
    diags = case_dict_key_diagnostics(
        tmp_path,
        catalogued_paths=("ecgDomains.<name>.sigmaExtracellular",),
        dict_relpaths=("constant/electroProperties",),
    )
    assert [d.field for d in diags] == ["sigmaExtracellulr"]
