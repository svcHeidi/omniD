"""The ionic-model axis: ``ionic_model_axis(name, *, document, scope)`` maps an ionic-model name to its
``<solver>Coeffs.ionicModel`` and ``singleCellStimulus.stim_amplitude`` patches, both from the ionic model catalog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult


def ionic_model_axis(
    name: str, *, document: str, scope: tuple[str, ...],
) -> AxisContract:
    """Build a named axis mapping an ionic model's name to its
    ``ionicModel``/``singleCellStimulus.stim_amplitude`` patches.

    ``document`` is the case-relative document the ``<solver>Coeffs`` scope
    lives in. ``scope`` is the dictionary path to that block (e.g.
    ``("singleCellSolverCoeffs",)``).

    The amplitude is looked up, never study-supplied: it is a property of the
    model, so a second study value would restate the same fact.

    Refuses by name a model the ionic model catalog does not recognise, or
    one with no single-cell stimulus amplitude declared (every
    manufactured-tissue-only model).
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        model_name = value
        entry = IONIC_MODEL_CATALOG.get(model_name)
        if entry is None:
            raise ValueError(
                f"ionic-model axis {name!r}: {model_name!r} is not a model "
                f"the ionic model catalog knows (known models: "
                f"{sorted(IONIC_MODEL_CATALOG)})"
            )
        amplitude = entry.single_cell_stimulus_amplitude
        if amplitude is None:
            raise ValueError(
                f"ionic-model axis {name!r}: {model_name!r} declares no "
                "single_cell_stimulus_amplitude in the ionic model catalog "
                "(typically a manufactured-only verification model, which "
                "has no single-cell case) -- there is no stimulus amplitude "
                "to derive, so this model cannot be used with this axis"
            )
        ionic_model_patch = AxisPatch(
            document=document,
            key_path=scope + ("ionicModel",),
            value=model_name,
            value_kind="word",
        )
        stim_amplitude_patch = AxisPatch(
            document=document,
            key_path=scope + ("singleCellStimulus", "stim_amplitude"),
            value=amplitude,
            value_kind="scalar",
        )
        return AxisResult(patches=(ionic_model_patch, stim_amplitude_patch))

    return AxisContract(name=name, value_kind="word", resolve=resolve)
