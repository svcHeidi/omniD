"""How ``omnidriver check`` exercises each cardiacCore record briefly against the real utilities.
``humanSlab`` needs its anatomy bundle: ``--input anatomy=<dir>``."""
from __future__ import annotations

from omnidriver.core.conformance_study import ConformanceStudy

_HUMAN_SLAB_UTILITIES = ("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeSlab", "setPurkinjeMorphometry")

# Every idealized-heart variant shares one native mesh (no supplied input at all) and one physics
# phase (setCardiacConductivity + setCardiacAnatomy), so their patch and sweep keys are the same
# real, pre-existing `setCardiacAnatomyDict` entries.
_IDEALIZED = dict(
    base_study={},
    patch=("system/setCardiacAnatomyDict:zApicalMid", 0.30),
    untouched=("system/setCardiacAnatomyDict", ("zMidBasal",)),
    sweep_name="system/setCardiacAnatomyDict:zApexCap",
    sweep_values=(0.06, 0.10),
    unknown_name="system/setCardiacAnatomyDict:zApicalMi",
    timeout_s=300.0,
)

STUDIES: dict[str, ConformanceStudy] = {
    "humanSlab": ConformanceStudy(
        requires=_HUMAN_SLAB_UTILITIES,
        base_study={},
        # Both keys are in the native dict (`thickness 0.1;`, `multiplier 3.0;`).
        patch=("system/setPurkinjeSlabDict:thickness", 0.2),
        untouched=("system/setCardiacAnatomyDict", ("zApicalMid",)),
        sweep_name="system/setPurkinjeSlabDict:multiplier",
        sweep_values=(2.0, 4.0),
        unknown_name="system/setPurkinjeSlabDict:thicknes",
        # Real utilities over a real anatomy bundle; generous but bounded.
        timeout_s=900.0,
    ),
    "idealizedHeart": ConformanceStudy(requires=_HUMAN_SLAB_UTILITIES, **_IDEALIZED),
    "idealizedHeartEndocardial": ConformanceStudy(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "generatePurkinjeTree"), **_IDEALIZED,
    ),
    "idealizedHeartPigTransmural": ConformanceStudy(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeMorphometry", "generatePurkinjeTree"),
        **_IDEALIZED,
    ),
}
