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
#     test_ionic_heterogeneity
#
# Description
#     Tests ionic heterogeneity logic and specification contracts.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Phase 2 — driverFOAM tissue-heterogeneity wiring.

Covers the four surfaces wired in Phase 2:
  1. ionic_model_catalog: ``supports_heterogeneity`` and
     ``supports_gradient_axis_heterogeneity`` flags plus tissue semantics.
  2. dict_entries: the five transmural ``ionicHeterogeneity.*`` DictEntries
     plus the five dynamic ``gradientAxes.<axis_name>.*`` entries (13 total
     with the three ``regions.<region_name>.*`` entries, separately gated).
  3. dict_builder: build + parse round-trip of a heterogeneity block
     (proves the generic nested-path machinery needs no builder change).
  4. validation: model-capability gates, named-region range checks,
     gradient-axis numeric constraints, tissue compat.

Corrected 2026-09-26 (catalog drift fix, final review AB Q7): this used to
cover ``apexBaseBands`` and ``endoMInterface``/``mEpiInterface`` plus the
``transmuralBands`` mode. Native ``3025230b9`` renamed ``apexBaseBands`` to
the dynamic-name ``gradientAxes`` (any number of named axes, not one fixed
block); native ``c7d6dd551`` deleted ``endoMInterface``/``mEpiInterface`` and
the ``transmuralBands`` mode outright, with no replacement -- ``mode`` is now
``namedRegions`` or ``cellZoneRegions`` only. Every test below that exercised
a deleted key is deleted, not weakened; every test that exercised
``apexBaseBands`` is reworked against ``gradientAxes.<axis_name>``, its exact
native replacement.
"""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.runtime.run_model import RunDocument
from omnidriver.core.specs.validation import validate_run

# validate_run now takes a mandatory driver_context
# (test_core_context_is_explicit.py); this file is cardiac ionic-model
# vocabulary throughout, so the cardiac context reproduces the previous
# implicit default exactly.
_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:ionic_heterogeneity",
)

_NATIVE_TISSUE_MODELS = ("BuenoOrovio", "TNNP", "TWorld", "ToRORd_dynCl")
_OVERRIDE_ONLY_TISSUE_MODELS = (
    "AlievPanfilov", "Courtemanche", "Fabbri", "Gaur",
    "Grandi", "PerisYague", "Stewart", "Trovato",
)


# --------------------------------------------------------------------------
# 1) Catalog flags
# --------------------------------------------------------------------------

def test_supports_heterogeneity_flag_for_capable_scalar_models():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in ("BuenoOrovio", "TNNP", "TWorld", "ToRORd_dynCl"):
        assert IONIC_MODEL_CATALOG[name].supports_heterogeneity is True, name


def test_supports_heterogeneity_inherited_by_batched_variants():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "BuenoOroviocompactBatched", "TNNPcompactBatched",
        "TWorldcompactBatched", "ToRORd_dynClcompactBatched",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_heterogeneity is True, name


def test_single_tissue_models_do_not_support_heterogeneity():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "monodomainFDAManufactured", "bidomainFDAManufactured",
        "bathBidomainFDAManufactured",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_heterogeneity is False, name


def test_supports_gradient_axis_heterogeneity_for_capable_scalar_models():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in ("BuenoOrovio", "TNNP", "TWorld", "ToRORd_dynCl"):
        assert IONIC_MODEL_CATALOG[name].supports_gradient_axis_heterogeneity is True, name


def test_supports_gradient_axis_heterogeneity_inherited_by_batched_variants():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "BuenoOroviocompactBatched", "TNNPcompactBatched",
        "TWorldcompactBatched", "ToRORd_dynClcompactBatched",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_gradient_axis_heterogeneity is True, name


def test_native_tissue_labels_mark_models_with_intrinsic_tissue_variants():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    expected = ("epicardialCells", "mCells", "endocardialCells")
    for name in _NATIVE_TISSUE_MODELS:
        assert IONIC_MODEL_CATALOG[name].native_tissue_labels == expected, name
        assert IONIC_MODEL_CATALOG[name].approximate_tissue_labels == (), name


def test_override_only_models_advertise_approximate_tissue_labels_explicitly():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    expected = ("epicardialCells", "mCells", "endocardialCells")
    for name in _OVERRIDE_ONLY_TISSUE_MODELS:
        assert IONIC_MODEL_CATALOG[name].native_tissue_labels == ("myocyte",), name
        assert IONIC_MODEL_CATALOG[name].approximate_tissue_labels == expected, name


def test_default_single_cell_tissue_map_uses_native_tissues_only():
    from omnidriver.cardiacfoam.tutorials.defaults.single_cell import IONIC_MODEL_TISSUE_MAP
    assert IONIC_MODEL_TISSUE_MAP["BuenoOrovio"] == (
        "epicardialCells", "mCells", "endocardialCells",
    )
    assert IONIC_MODEL_TISSUE_MAP["Gaur"] == ("myocyte",)


def test_planning_tissues_uses_native_tissues_only_for_other_models():
    """`restitutionCurves`'s own defaults module (which used to duplicate
    `single_cell`'s `IONIC_MODEL_TISSUE_MAP` construction verbatim) was
    deleted 2026-09-25 when that tutorial migrated onto a tutorial record
    (docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md) --
    its `restitutionCurvesIonicModelAxis` now derives `tissue` from the same
    `planning_tissues()` helper directly. This proves that helper's own
    behaviour for two more models (`TNNP`/`Courtemanche`) the test above
    does not cover, independent of any tutorial-specific module."""
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG, planning_tissues
    assert planning_tissues(IONIC_MODEL_CATALOG["TNNP"]) == (
        "epicardialCells", "mCells", "endocardialCells",
    )
    assert planning_tissues(IONIC_MODEL_CATALOG["Courtemanche"]) == ("myocyte",)


def test_manufactured_models_do_not_support_gradient_axis_heterogeneity():
    # These models support neither transmural/named-region nor apex-base
    # heterogeneity at all — the manufactured verification models.
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "monodomainFDAManufactured", "bidomainFDAManufactured",
        "bathBidomainFDAManufactured",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_gradient_axis_heterogeneity is False, name


# --------------------------------------------------------------------------
# 2) dict_entries
# --------------------------------------------------------------------------

def _het_entries():
    from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
    return get_electro_property_entry_groups(_CTX)["ionic_heterogeneity"]


def _transmural_entries():
    return [
        e for e in _het_entries()
        if not e.driver_path.startswith("$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.gradientAxes.")
    ]


def _gradient_axes_entries():
    return [
        e for e in _het_entries()
        if e.driver_path.startswith("$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.gradientAxes.")
    ]


def test_all_thirteen_heterogeneity_entries_exist():
    paths = {e.driver_path for e in _het_entries()}
    transmural_leaves = (
        "field", "mode", "transitionWidth", "transitionMode", "smoothing",
    )
    ga_leaves = (
        "gradientAxes.<axis_name>.field", "gradientAxes.<axis_name>.beta",
        "gradientAxes.<axis_name>.scalingMin", "gradientAxes.<axis_name>.scalingMax",
        "gradientAxes.<axis_name>.variables",
    )
    region_leaves = (
        "regions.<region_name>.baseline",
        "regions.<region_name>.cellZone",
        "regions.<region_name>.range",
    )
    expected = {
        f"$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.{leaf}"
        for leaf in (*transmural_leaves, *ga_leaves, *region_leaves)
    }
    assert paths == expected


def test_transmural_entries_gated_to_spatial_solvers():
    """Transmural ionicHeterogeneity entries must fire for all spatial EP solvers."""
    for e in _transmural_entries():
        assert e.applicable_when.get("$ionicHeterogeneity_supported") is True, e.driver_path


def test_gradient_axes_entries_gated_to_monodomain_and_bidomain():
    """gradientAxes entries apply to monodomainSolver and bidomainSolver.

    Both dispatch through the same myocardiumDomainInterface::New() codepath
    (myocardiumDomainInterface.C) that parses ionicHeterogeneity.gradientAxes;
    eikonalSolver returns early from that factory before ionic-model/heterogeneity
    setup runs, and singleCellSolver bypasses the factory entirely.
    """
    for e in _gradient_axes_entries():
        assert e.applicable_when.get("myocardiumSolver") == (
            "monodomainSolver", "bidomainSolver",
        ), e.driver_path


def test_heterogeneity_enum_values():
    by_leaf = {e.driver_path.rsplit(".", 1)[-1]: e for e in _het_entries()}
    assert set(by_leaf["mode"].enum_values) == {"namedRegions", "cellZoneRegions"}
    assert by_leaf["transitionMode"].enum_values == ("blend", "hard")
    assert by_leaf["smoothing"].enum_values == ("smoothstep",)


def test_gradient_axes_numeric_constraints():
    by_leaf = {e.driver_path.rsplit(".", 1)[-1]: e for e in _gradient_axes_entries()}
    assert any("scalingMax" in c for c in by_leaf["scalingMin"].constraints)
    assert any("> 0" in c for c in by_leaf["scalingMin"].constraints)


def test_heterogeneity_entries_are_optional():
    for e in _het_entries():
        assert e.required is False


# --------------------------------------------------------------------------
# 3) dict_builder round-trip (no builder code change required)
# --------------------------------------------------------------------------

_HET_OVERRIDES = {
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.field": "t",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.mode": "namedRegions",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.endocardialCells.range": "(0 0.3)",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.mCells.range": "(0.3 0.7)",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.epicardialCells.range": "(0.7 1)",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionWidth": "0.1",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionMode": "blend",
    "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.smoothing": "smoothstep",
}


def test_build_emits_nested_heterogeneity_block():
    from omnidriver.cardiacfoam.dict_builder import build_electro_properties
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "BuenoOrovio",
            "tissue": "epicardialCells",
        },
        overrides=_HET_OVERRIDES,
    )
    assert "ionicHeterogeneity" in text
    assert "mode namedRegions;" in text
    assert "transitionMode blend;" in text


def test_build_then_parse_round_trips_heterogeneity(tmp_path):
    from omnidriver.cardiacfoam.dict_builder import (
        build_electro_properties,
        parse_electro_properties,
    )
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "BuenoOrovio",
            "tissue": "epicardialCells",
        },
        overrides=_HET_OVERRIDES,
    )
    path = tmp_path / "electroProperties"
    path.write_text(text)

    parsed = parse_electro_properties(path)
    overrides = parsed["overrides"]
    for key, value in _HET_OVERRIDES.items():
        assert overrides.get(key) == value, key


def test_default_build_omits_heterogeneity_block():
    # Heterogeneity must be opt-in: a capable model with no het overrides
    # produces no ionicHeterogeneity block.
    from omnidriver.cardiacfoam.dict_builder import build_electro_properties
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "BuenoOrovio",
            "tissue": "epicardialCells",
        },
    )
    assert "ionicHeterogeneity" not in text


# --------------------------------------------------------------------------
# 4) Validation
# --------------------------------------------------------------------------

def _run(physics: dict) -> RunDocument:
    config = {"anatomy": {}, "physics": physics, "stimulus": {}, "solver": {}}
    return RunDocument(id="r1", name="r", status="draft", config=config, configurationSource="document")


def test_heterogeneity_with_incapable_model_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "monodomainFDAManufactured",
        "tissue": "manufactured",
        "ionicHeterogeneity.field": "t",
        "ionicHeterogeneity.mode": "transmuralBands",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX)
              if e.level == "error" and "heterogeneity" in e.message.lower()]
    assert len(errors) == 1, [e.message for e in validate_run(run, driver_context=_CTX)]


def test_heterogeneity_with_capable_model_no_het_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "BuenoOrovio",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.field": "t",
        "ionicHeterogeneity.mode": "namedRegions",
    })
    het_errors = [e for e in validate_run(run, driver_context=_CTX)
                  if e.level == "error" and "heterogeneity" in e.message.lower()]
    assert het_errors == []


# endoMInterface/mEpiInterface ordering tests were deleted 2026-09-26 (catalog
# drift fix): native c7d6dd551 removed both keys and the transmuralBands mode
# that used them, with no replacement -- there is nothing left to order.


def test_tissue_incompatible_with_model_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "AlievPanfilovcompactBatched",   # myocyte-only (not yet wired for heterogeneity)
        "tissue": "epicardialCells",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX)
              if e.level == "error" and "compatible tissues" in e.message]
    assert len(errors) == 1, [e.message for e in validate_run(run, driver_context=_CTX)]


def test_tissue_compatible_with_model_is_silent():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "BuenoOrovio",
        "tissue": "epicardialCells",
    })
    issues = [e for e in validate_run(run, driver_context=_CTX) if "compatible tissues" in e.message]
    assert issues == []


# --------------------------------------------------------------------------
# 5) Gradient-axis heterogeneity validation
#
# Corrected 2026-09-26 (catalog drift fix): reworked from "apex-to-base
# heterogeneity validation" against the deleted apexBaseBands.* keys onto
# gradientAxes.<axis_name>.*, its exact native replacement (3025230b9). The
# beta>0 tests are deleted, not reworked: validateGradientAxisConfig
# (ionicHeterogeneity.C) never constrained beta, only scalingMin/scalingMax/
# variables, so that check was never backed by a native read.
# --------------------------------------------------------------------------

def test_gradient_axes_with_incapable_model_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "bidomainFDAManufactured",
        "tissue": "myocyte",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX)
              if e.level == "error" and "gradient-axis" in e.message]
    assert len(errors) == 1, [e.message for e in validate_run(run, driver_context=_CTX)]


def test_gradient_axes_with_capable_model_no_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.beta": "3.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMin": "0.2",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMax": "5.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    ga_errors = [e for e in validate_run(run, driver_context=_CTX)
                 if e.level == "error" and "gradientaxes" in e.message.lower()]
    assert ga_errors == []


def test_gradient_axes_negative_beta_is_silent():
    """beta carries no native constraint (apexBaseScale accepts any value);
    a negative beta must not be rejected."""
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.beta": "-1.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX) if "beta" in e.message]
    assert errors == []


def test_gradient_axes_scalingMin_must_not_exceed_scalingMax():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMin": "8.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMax": "2.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX)
              if e.level == "error" and "scalingMin" in e.message]
    assert len(errors) == 1


def test_gradient_axes_valid_scaling_range_is_silent():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMin": "0.2",
        "ionicHeterogeneity.gradientAxes.apicobasal.scalingMax": "5.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX) if "scalingMin" in e.message]
    assert errors == []


def test_gradient_axes_empty_variables_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "()",
    })
    errors = [e for e in validate_run(run, driver_context=_CTX)
              if e.level == "error" and "variables" in e.message]
    assert len(errors) == 1


def test_transmural_and_gradient_axes_can_coexist():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.field": "t",
        "ionicHeterogeneity.mode": "namedRegions",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.beta": "3.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    het_errors = [
        e for e in validate_run(run, driver_context=_CTX)
        if e.level == "error" and "heterogeneity" in e.message.lower()
    ]
    assert het_errors == []
