"""Metadata of the ionic model catalogue: identity of Gaur, and what each full model recommends exporting."""

from __future__ import annotations

import unittest

from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG


def test_gaur_metadata_matches_selected_source_identity() -> None:
    """Gaur_2021.H calls this a pig ventricular model, not guinea-pig/Rudy."""
    gaur = IONIC_MODEL_CATALOG["Gaur"]
    assert gaur.species == ("pig",)
    assert gaur.cardiac_region == ("ventricle",)
    assert gaur.description.startswith("Pig ventricular ionic model (Gaur 2021).")
    assert gaur.aliases == ("Gaur 2021", "pig ventricular model")


_FULL_IONIC_MODELS = {
    "TNNP", "Grandi", "Courtemanche", "Fabbri",
    "ToRORd_dynCl", "Trovato", "Stewart", "Gaur", "PerisYague", "TWorld",
}

# V/Ca aliases in recommended_exports that match no state/algebraic name (TNNP, Grandi, Trovato, Stewart).
_ALLOWED_LEGACY_TOKENS: set[str] = {
    "membrane_V", "calcium_Cai",
    "Cass",
    "Vm",
    "V", "Cai",
}


class TestRecommendedExportsExpanded(unittest.TestCase):
    """Full ionic models expose >= 4 recommended exports."""

    def test_full_models_have_at_least_four_exports(self) -> None:
        for name in _FULL_IONIC_MODELS:
            with self.subTest(model=name):
                entry = IONIC_MODEL_CATALOG[name]
                self.assertGreaterEqual(
                    len(entry.recommended_exports),
                    4,
                    f"{name}.recommended_exports has only "
                    f"{len(entry.recommended_exports)} entries (< 4)",
                )

    def test_recommended_exports_tokens_in_states_or_algebraic(self) -> None:
        for name in _FULL_IONIC_MODELS:
            with self.subTest(model=name):
                entry = IONIC_MODEL_CATALOG[name]
                valid = set(entry.states) | set(entry.algebraic)
                bad = [
                    tok
                    for tok in entry.recommended_exports
                    if tok not in valid and tok not in _ALLOWED_LEGACY_TOKENS
                ]
                self.assertEqual(
                    bad,
                    [],
                    f"{name}.recommended_exports contains tokens not in "
                    f"states/algebraic (and not in allowed legacy set): {bad}",
                )


class TestRecommendedExportsExpansion(unittest.TestCase):
    """recommended_exports is the fallback when no ``outputVariables.ionic.export`` is declared, so it must be informative."""

    _FULL_IONIC_MODELS: frozenset[str] = frozenset({
        "TNNP", "Grandi", "Courtemanche", "Fabbri",
        "ToRORd_dynCl", "Trovato", "Stewart", "Gaur",
        "PerisYague", "TWorld",
    })

    def test_every_full_model_has_at_least_5_exports(self) -> None:
        """5 = voltage + calcium + 3 currents, a floor."""
        for name in self._FULL_IONIC_MODELS:
            with self.subTest(model=name):
                entry = IONIC_MODEL_CATALOG[name]
                self.assertGreaterEqual(
                    len(entry.recommended_exports), 5,
                    f"{name}.recommended_exports has only "
                    f"{len(entry.recommended_exports)} tokens — "
                    f"expected at least 5 (Vm + Cai + 3 currents).",
                )

    def test_full_model_exports_include_total_ionic_current(self) -> None:
        for name in self._FULL_IONIC_MODELS:
            with self.subTest(model=name):
                entry = IONIC_MODEL_CATALOG[name]
                has_total = any(
                    "Iion" in token for token in entry.recommended_exports
                )
                self.assertTrue(
                    has_total,
                    f"{name}.recommended_exports lacks a total-ionic-current "
                    f"token (Iion / Iion_cm): {entry.recommended_exports}",
                )


if __name__ == "__main__":
    unittest.main()
