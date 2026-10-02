"""Region-specific ionic overrides. The solver (``ionicModelIO.C``) applies
``global`` first, then the one tissue scope matching each cell's tissue flag:
epicardialCells, mCells, endocardialCells or myocyte.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.dict_builder import build_electro_properties

_SELECTORS = {
    "myocardiumSolver": "singleCellSolver",
    "ionicModel": "TNNP",
    "tissue": "epicardialCells",
}


@pytest.mark.parametrize(
    "scope", ["global", "epicardialCells", "mCells", "endocardialCells", "myocyte"]
)
def test_every_solver_recognised_scope_is_writable(scope):
    text = build_electro_properties(
        selectors=_SELECTORS,
        overrides={
            f"$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.{scope}.scale.g_Kr": "0.5"
        },
    )
    assert scope in text
    assert "g_Kr" in text


def test_global_and_a_tissue_scope_compose_as_the_solver_applies_them():
    text = build_electro_properties(
        selectors=_SELECTORS,
        overrides={
            "$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.global.scale.g_Na": "0.2",
            "$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.epicardialCells.scale.g_to": "6.0",
            "$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.epicardialCells.scale.g_CaL": "0.5",
        },
    )
    assert "global" in text and "epicardialCells" in text
    for name in ("g_Na", "g_to", "g_CaL"):
        assert name in text


def test_set_is_writable_per_scope_too():
    text = build_electro_properties(
        selectors=_SELECTORS,
        overrides={
            "$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.endocardialCells.set.g_Ks": "0.098"
        },
    )
    assert "endocardialCells" in text and "g_Ks" in text


def test_unprefixed_tnnp_constant_names_are_accepted():
    text = build_electro_properties(
        selectors=_SELECTORS,
        overrides={
            "$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.global.scale.g_Kr": "0.5"
        },
    )
    assert "g_Kr" in text
    assert "AC_g_Kr" not in text
