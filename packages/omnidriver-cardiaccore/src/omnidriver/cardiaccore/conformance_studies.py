"""How ``omnidriver check`` exercises each cardiacCore record briefly against the real utilities."""
from __future__ import annotations

from omnidriver.core.conformance_study import ConformanceStudy

_SLAB_VARIANT_UTILITIES = ("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeSlab", "setPurkinjeMorphometry")

# Every idealized-heart variant shares one native mesh (no supplied input at all) and one physics
# phase (setCardiacConductivity + setCardiacAnatomy), so their patch and sweep keys are the same
# real, pre-existing `setCardiacConductivityDict` entries (`setCardiacAnatomyDict` is empty).
_IDEALIZED = dict(
    base_study={},
    patch=("system/setCardiacConductivityDict:df", 0.12),
    untouched=("system/setCardiacConductivityDict", ("ds",)),
    sweep_name="system/setCardiacConductivityDict:dn",
    sweep_values=(0.012, 0.016),
    unknown_name="system/setCardiacConductivityDict:dff",
    timeout_s=300.0,
)

STUDIES: dict[str, ConformanceStudy] = {
    "idealizedHeart": ConformanceStudy(requires=_SLAB_VARIANT_UTILITIES, **_IDEALIZED),
    "idealizedHeartEndocardial": ConformanceStudy(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "generatePurkinjeTree"), **_IDEALIZED,
    ),
    "idealizedHeartPigTransmural": ConformanceStudy(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeMorphometry", "generatePurkinjeTree"),
        **_IDEALIZED,
    ),
}
