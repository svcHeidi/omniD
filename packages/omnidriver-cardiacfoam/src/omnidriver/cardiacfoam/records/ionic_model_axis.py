"""The ionic-model axis (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``,
step 4b -- the pilot, ``restitutionCurves``).

The owner's own instruction for this axis: "the model name gives
``<solver>Coeffs.ionicModel`` plus ``singleCellStimulus.stim_amplitude`` from
the catalog field. Refuse a model with no amplitude, or one the catalog does
not know."

A parameterised BUILDER (``ionic_model_axis(name, *, document, scope)``), the
same shape ``omnidriver.openfoam.axes.block_mesh_resolution
.block_mesh_resolution_axis`` already uses: this module knows the
``electroProperties`` grammar and the ionic model catalog, not any
particular tutorial's own choice of document or ``<solver>Coeffs`` scope --
a tutorial record (``restitutionCurves``, step 4b) instantiates this builder
with its own ``document``/``scope`` and registers the result under whatever
name it allows.

Why the catalog lookup, not a study-supplied amplitude: the amplitude is a
property OF the model (§1's own STIMULUS_MAP rule, now
``IonicModelEntry.single_cell_stimulus_amplitude``), not something a caller
picks independently of which model it names -- a study naming a model and a
separate, disagreeing amplitude would just be restating the same fact
twice, wrongly. Keeping this axis's OWN study value a bare model name (never
a mapping of {model, amplitude}) means there is exactly one thing to name,
and the catalog is asked, never told.

Two document keys per resolution, both under the tutorial's own
``<solver>Coeffs`` scope (``scope``, e.g. ``("singleCellSolverCoeffs",)``):
``scope + ("ionicModel",)`` (the model name itself) and
``scope + ("singleCellStimulus", "stim_amplitude")`` (the catalog's
amplitude for that model). ``tissue`` is NOT one of them -- design's own
instruction for step 4b: "tissue is set as a direct key in the study; do
not derive it," so a record's own study supplies it directly, never through
this or any other axis.
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
    lives in (``restitutionCurves`` uses ``"constant/electroProperties"``).
    ``scope`` is the dictionary path to that ``<solver>Coeffs`` block (e.g.
    ``("singleCellSolverCoeffs",)``) -- this axis does not derive it from
    ``myocardiumSolver``, since that value is not itself varied by this
    tutorial (design's own accounting: the native case already holds it).

    The axis declares ``value_kind="word"`` for the STUDY value it accepts
    (a bare model name) -- checked by ``tutorial_records
    .resolve_case_patches`` before ``resolve`` ever runs, so a non-string or
    whitespace-containing value is refused by core's own generic shape
    check before reaching this module's code at all.

    Refuses by name (module docstring has the reasoning):

    - a model name the ionic model catalog does not recognise at all;
    - a model recognised by the catalog but with no single-cell stimulus
      amplitude declared (``single_cell_stimulus_amplitude is None`` --
      every ``"manufactured"``-tissue-only model, by construction: there is
      no single-cell case for a manufactured verification model).
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
