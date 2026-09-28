"""Regression for OpenFOAM value quoting: an unquoted ``3D`` made the built
electroProperties unparseable, so $ELECTRO_MODEL_COEFFS.dimension was unusable."""

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
