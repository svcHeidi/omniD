"""End-to-end regression for the OpenFOAM value-quoting fix: this exact
value produced an unparseable dictionary through the cardiac dict builder,
making $ELECTRO_MODEL_COEFFS.dimension unusable through the driver. Found
by running listCellModelsVariables for real."""

from __future__ import annotations

from omnidriver.cardiacfoam.dict_builder import build_electro_properties


def test_dimension_reaches_the_dict_in_a_form_openfoam_can_parse():
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "singleCellSolver",
            "ionicModel": "monodomainFDAManufactured",
            "tissue": "myocyte",
        },
        overrides={"$ELECTRO_MODEL_COEFFS.dimension": "3D"},
    )
    assert 'dimension "3D";' in text
    assert "dimension 3D;" not in text
