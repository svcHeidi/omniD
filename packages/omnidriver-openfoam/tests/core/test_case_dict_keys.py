"""Warn-level sweep of a case dictionary's keys against the plugin catalogue
-- the direction the C++ scanner cannot see, since a key nobody catalogued
is silently ignored by OpenFOAM rather than appearing anywhere in C++."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.case_dict_keys import case_dict_key_diagnostics
from omnidriver.core.specs.paths import repo_root_default
from conftest import monorepo_root, skip_without_monorepo

_SINGLE_CELL = (
    (monorepo_root or repo_root_default())
    / "tutorials" / "electrophysiologyProtocols" / "singleCell"
)

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


@pytest.mark.parametrize("skip", [False, True])
def test_missing_or_explicitly_skipped_file_is_silent(tmp_path, monkeypatch, skip):
    if skip:
        _write(tmp_path, "malformed {")
        monkeypatch.setenv("SKIP_CASE_DICT_KEY_DIAGNOSTICS", "1")
    else:
        monkeypatch.delenv("SKIP_CASE_DICT_KEY_DIAGNOSTICS", raising=False)

    def unexpected_read(path):
        pytest.fail("missing or skipped dictionaries must not be read")

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


# ---------------------------------------------------------------------------
# Wiring into the strict plan: reported, but never fatal
# ---------------------------------------------------------------------------


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


@skip_without_monorepo
def test_strict_plan_reports_a_misspelled_key_without_failing(tmp_path):
    # cardiacFoam does not own every key that may appear in these dicts, so
    # an unmatched key can never be allowed to fail a plan.
    import shutil

    from omnidriver.core.plugin_interface import default_driver_context
    from omnidriver.core.strict_planning import strict_plan

    cases_root = tmp_path / "tutorials"
    case = cases_root / "case"
    shutil.copytree(_SINGLE_CELL, case)
    ep = case / "constant" / "electroProperties"
    ep.write_text(
        ep.read_text().replace(
            "activeTensionModel LandNiederer;",
            "activeTensionModl LandNiederer;",
        )
    )

    report = strict_plan(
        "case",
        entry_kind="case_folder",
        overrides={"cases_root": str(cases_root)},
        environment_source="/no/such/openfoam/bashrc",
        driver_context=default_driver_context(),
    )
    payload = report.to_json()

    warnings = [
        item
        for item in payload["case_dict_key_diagnostics"]
        if item["code"] == "uncatalogued_case_dict_key"
    ]
    assert [w["field"] for w in warnings] == ["activeTensionModl"]
    assert all(w["level"] == "warning" for w in warnings)

    # Warn-only: the key diagnostics must not appear in any error bucket.
    for bucket in ("validation_diagnostics", "catalog_coverage_errors"):
        assert not [
            item
            for item in payload[bucket]
            if item["code"] == "uncatalogued_case_dict_key"
        ]


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


# ---------------------------------------------------------------------------
# Why required_when can never catch this, and the warning is the only signal
# ---------------------------------------------------------------------------


@skip_without_monorepo
def test_a_misspelled_key_is_silently_replaced_by_the_catalogue_default(tmp_path):
    # stim_amplitude's required_when rule is live but cannot fire here: the
    # builder fills every entry's typical_value before validation runs, so a
    # key carrying one is structurally immune to the required-field check.
    import shutil

    from omnidriver.cardiacfoam import dict_builder as DB
    from omnidriver.core.plugin_interface import default_driver_context
    from omnidriver.core.strict_planning import strict_plan

    cases_root = tmp_path / "tutorials"
    case = cases_root / "case"
    shutil.copytree(_SINGLE_CELL, case)
    ep = case / "constant" / "electroProperties"
    ep.write_text(ep.read_text().replace("stim_amplitude  60;", "stim_amplitud  25;"))

    parsed = DB.parse_electro_properties(ep)
    rebuilt = str(
        DB.build_electro_properties(
            selectors=parsed["selectors"], overrides=parsed["overrides"]
        )
    )
    amplitude = [l.strip() for l in rebuilt.splitlines() if "stim_amplitude" in l]
    assert amplitude == ["stim_amplitude 60;"], (
        f"expected the catalogue default to be substituted, got {amplitude}"
    )
    assert "stim_amplitud " not in rebuilt, "the misspelled key is dropped entirely"

    payload = strict_plan(
        "case",
        entry_kind="case_folder",
        overrides={"cases_root": str(cases_root)},
        environment_source="/no/such/openfoam/bashrc",
        driver_context=default_driver_context(),
    ).to_json()

    # The plan is valid -- the built dict really is complete and correct.
    assert payload["status"] == "ok"
    assert not [
        item
        for item in payload["validation_diagnostics"]
        if "stim_amplitude" in item["message"]
    ], "required_when cannot fire here; if it starts to, this test should change"

    # ...and the warning is the only thing that noticed.
    assert [
        item["field"] for item in payload["case_dict_key_diagnostics"]
    ] == ["stim_amplitud"]
