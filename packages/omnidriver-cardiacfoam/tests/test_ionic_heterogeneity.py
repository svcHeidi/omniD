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

"""Tissue-heterogeneity wiring: catalog flags, ``ionicHeterogeneity.*`` dict entries, builder round-trip, validation.

Native ``mode`` is ``namedRegions`` or ``cellZoneRegions``; gradient axes are dynamically named ``gradientAxes.<axis_name>``.
"""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.runtime.run_model import RunDocument
from omnidriver.cardiacfoam.validation import cross_field_diagnostics

_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:ionic_heterogeneity",
)

def _cross_field(run):
    return cross_field_diagnostics({
        key: value for slice_ in run.config.values() for key, value in slice_.items()
        if value not in (None, "")
    })


_NATIVE_TISSUE_MODELS = ("BuenoOrovio", "TNNP", "TWorld", "ToRORd_dynCl")
_OVERRIDE_ONLY_TISSUE_MODELS = (
    "AlievPanfilov", "Courtemanche", "Fabbri", "Gaur",
    "Grandi", "PerisYague", "Stewart", "Trovato",
)


# Catalog flags

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


def test_planning_tissues_uses_native_tissues_only_for_other_models():
    """``planning_tissues`` (which ``restitutionCurvesIonicModelAxis`` derives ``tissue`` from) for TNNP and Courtemanche."""
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG, planning_tissues
    assert planning_tissues(IONIC_MODEL_CATALOG["TNNP"]) == (
        "epicardialCells", "mCells", "endocardialCells",
    )
    assert planning_tissues(IONIC_MODEL_CATALOG["Courtemanche"]) == ("myocyte",)


def test_manufactured_models_do_not_support_gradient_axis_heterogeneity():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "monodomainFDAManufactured", "bidomainFDAManufactured",
        "bathBidomainFDAManufactured",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_gradient_axis_heterogeneity is False, name


# dict_entries

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
    for e in _transmural_entries():
        assert e.applicable_when.get("$ionicHeterogeneity_supported") is True, e.driver_path


def test_gradient_axes_entries_gated_to_monodomain_and_bidomain():
    """Only these reach ``myocardiumDomainInterface::New()``; eikonalSolver returns early and singleCellSolver bypasses it."""
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


# dict_builder round-trip

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
    from omnidriver.cardiacfoam.dict_builder import build_electro_properties
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "BuenoOrovio",
            "tissue": "epicardialCells",
        },
    )
    assert "ionicHeterogeneity" not in text


# Validation

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
    errors = [e for e in _cross_field(run)
              if e.level == "error" and "heterogeneity" in e.message.lower()]
    assert len(errors) == 1, [e.message for e in _cross_field(run)]


def test_heterogeneity_with_capable_model_no_het_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "BuenoOrovio",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.field": "t",
        "ionicHeterogeneity.mode": "namedRegions",
    })
    het_errors = [e for e in _cross_field(run)
                  if e.level == "error" and "heterogeneity" in e.message.lower()]
    assert het_errors == []


def test_tissue_incompatible_with_model_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "AlievPanfilovcompactBatched",   # myocyte-only
        "tissue": "epicardialCells",
    })
    errors = [e for e in _cross_field(run)
              if e.level == "error" and "compatible tissues" in e.message]
    assert len(errors) == 1, [e.message for e in _cross_field(run)]


def test_tissue_compatible_with_model_is_silent():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "BuenoOrovio",
        "tissue": "epicardialCells",
    })
    issues = [e for e in _cross_field(run) if "compatible tissues" in e.message]
    assert issues == []


# Gradient-axis heterogeneity validation

def test_gradient_axes_with_incapable_model_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "bidomainFDAManufactured",
        "tissue": "myocyte",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in _cross_field(run)
              if e.level == "error" and "gradient-axis" in e.message]
    assert len(errors) == 1, [e.message for e in _cross_field(run)]


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
    ga_errors = [e for e in _cross_field(run)
                 if e.level == "error" and "gradientaxes" in e.message.lower()]
    assert ga_errors == []


def test_gradient_axes_negative_beta_is_silent():
    """beta carries no native constraint: ``validateGradientAxisConfig`` checks only scalingMin/scalingMax/variables."""
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.beta": "-1.0",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "(g_Ks)",
    })
    errors = [e for e in _cross_field(run) if "beta" in e.message]
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
    errors = [e for e in _cross_field(run)
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
    errors = [e for e in _cross_field(run) if "scalingMin" in e.message]
    assert errors == []


def test_gradient_axes_empty_variables_is_error():
    run = _run({
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
        "ionicHeterogeneity.gradientAxes.apicobasal.field": "longitudinal",
        "ionicHeterogeneity.gradientAxes.apicobasal.variables": "()",
    })
    errors = [e for e in _cross_field(run)
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
        e for e in _cross_field(run)
        if e.level == "error" and "heterogeneity" in e.message.lower()
    ]
    assert het_errors == []
