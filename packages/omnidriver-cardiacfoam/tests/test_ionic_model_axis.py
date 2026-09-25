"""Step 4b (pilot ``restitutionCurves``) of docs/superpowers/specs/2026-09-24-
tutorials-are-pointers-design.md: the ionic-model axis.

Design's own words for this axis (owner instruction for step 4b, item 2):
"the model name gives ``<solver>Coeffs.ionicModel`` plus
``singleCellStimulus.stim_amplitude`` from the catalog field. Refuse a model
with no amplitude, or one the catalog does not know."

This axis is a parameterised BUILDER (``ionic_model_axis(name, *, document,
scope)``), the same shape as OpenFOAM's ``block_mesh_resolution_axis``: this
module knows the ``electroProperties`` grammar (a ``<solver>Coeffs`` scope's
``ionicModel``/``singleCellStimulus.stim_amplitude`` keys) and the ionic
model catalog, not any particular tutorial's choice of document/scope --
``restitutionCurves``'s own record registers this builder under its own
name, with ``document="constant/electroProperties"`` and
``scope=("singleCellSolverCoeffs",)``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records.ionic_model_axis import ionic_model_axis

_DOCUMENT = "constant/electroProperties"
_SCOPE = ("singleCellSolverCoeffs",)


def _axis():
    return ionic_model_axis("ionicModel", document=_DOCUMENT, scope=_SCOPE)


def _staged_case(tmp_path: Path) -> Path:
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "electroProperties").write_text("myocardiumSolver singleCellSolver;\n")
    return case_root


def test_axis_declares_a_word_value_kind():
    axis = _axis()
    assert axis.name == "ionicModel"
    assert axis.value_kind == "word"


def test_a_known_model_produces_ionic_model_and_stim_amplitude_patches(tmp_path):
    axis = _axis()
    case_root = _staged_case(tmp_path)

    result = axis.resolve("TWorld", case_root)

    by_key_path = {patch.key_path: patch for patch in result.patches}
    assert by_key_path[("singleCellSolverCoeffs", "ionicModel")].value == "TWorld"
    assert by_key_path[("singleCellSolverCoeffs", "ionicModel")].document == _DOCUMENT
    stim = by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")]
    assert stim.value == 60.0
    assert stim.document == _DOCUMENT


def test_bueno_orovio_confirms_the_native_amplitude(tmp_path):
    """The design's own migration note: BuenoOrovio's amplitude is 0.4,
    confirmed against the native singleCell tutorial's default case."""
    axis = _axis()
    case_root = _staged_case(tmp_path)

    result = axis.resolve("BuenoOrovio", case_root)

    by_key_path = {patch.key_path: patch for patch in result.patches}
    stim = by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")]
    assert stim.value == 0.4


def test_an_unknown_model_is_refused_by_name(tmp_path):
    axis = _axis()
    case_root = _staged_case(tmp_path)

    with pytest.raises(ValueError, match="NotAModel"):
        axis.resolve("NotAModel", case_root)


def test_a_manufactured_only_model_with_no_amplitude_is_refused_by_name(tmp_path):
    axis = _axis()
    case_root = _staged_case(tmp_path)

    with pytest.raises(ValueError, match="monodomainFDAManufactured"):
        axis.resolve("monodomainFDAManufactured", case_root)
