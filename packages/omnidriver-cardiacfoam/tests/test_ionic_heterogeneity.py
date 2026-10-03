"""Tissue-heterogeneity wiring: catalog flags, ``ionicHeterogeneity.*`` dict entries, builder round-trip, validation.

Native ``mode`` is ``namedRegions`` or ``cellZoneRegions``; gradient axes are dynamically named ``gradientAxes.<axis_name>``.
"""

from __future__ import annotations

from omnidriver.cardiacfoam.validation import cross_field_diagnostics


def _cross_field(config):
    return cross_field_diagnostics({
        key: value for slice_ in config.values() for key, value in slice_.items()
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


def test_manufactured_models_do_not_support_gradient_axis_heterogeneity():
    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
    for name in (
        "monodomainFDAManufactured", "bidomainFDAManufactured",
        "bathBidomainFDAManufactured",
    ):
        assert IONIC_MODEL_CATALOG[name].supports_gradient_axis_heterogeneity is False, name


# dict_entries

def _het_entries():
    from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
    return ELECTRO_PROPERTY_ENTRY_GROUPS["ionic_heterogeneity"]


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


def test_heterogeneity_entries_are_optional_except_what_a_declared_axis_must_set():
    axis_keys = {"beta", "scalingMin", "scalingMax", "variables"}
    for e in _het_entries():
        under_axis = ".gradientAxes.<axis_name>." in e.driver_path
        assert e.required is (under_axis and e.driver_path.rsplit(".", 1)[-1] in axis_keys), e.driver_path


# case_builder round-trip

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
    from omnidriver.cardiacfoam.case_builder import build_electro_properties
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


def test_default_build_omits_heterogeneity_block():
    from omnidriver.cardiacfoam.case_builder import build_electro_properties
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "BuenoOrovio",
            "tissue": "epicardialCells",
        },
    )
    assert "ionicHeterogeneity" not in text


# Validation

def _run(physics: dict) -> dict:
    config = {"anatomy": {}, "physics": physics, "stimulus": {}, "solver": {}}
    return config


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
