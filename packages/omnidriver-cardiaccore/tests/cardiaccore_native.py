"""Supplied inputs for native cardiacCore tests, and the conformance target
table. A uniquely named module, not ``conftest`` (CLAUDE.md's conftest trap).
Nothing here is discovered: the native tree comes from
``OMNIDRIVER_CARDIACCORE_TREE`` (a clean native worktree/archive, never the
owner's checkout, which has uncommitted work), the anatomy bundle from
``OMNIDRIVER_CARDIACCORE_ANATOMY``, and the OpenFOAM environment plus the
cardiacCore utilities, built from that tree's own committed source, from the
shell the tests run in (docs/solver-learning/cardiaccore.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.conformance import ConformanceTarget, require_commands, supplied_tree


def native_cardiaccore_tree() -> Path:
    return supplied_tree("OMNIDRIVER_CARDIACCORE_TREE")


def native_cardiaccore_anatomy() -> Path:
    """The ``humanSlab`` anatomy bundle: the mesh, ``fiber``, ``sheet`` and ``uvc_*`` fields that are not in the tracked case folder."""
    return supplied_tree("OMNIDRIVER_CARDIACCORE_ANATOMY")


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

# `requires` are the utilities the record's pipeline runs, on PATH from the sourced shell.
TARGETS: dict[str, dict[str, Any]] = {
    "humanSlab": dict(
        requires=_HUMAN_SLAB_UTILITIES,
        base_study={},
        # Both keys already exist in the native dict (`thickness 0.1;`, `multiplier 3.0;`):
        # `setPurkinjeMorphometryDict` declares none at all (relies on the compiled default),
        # and the renderer can only update an existing key, not insert one.
        patch=("system/setPurkinjeSlabDict:thickness", 0.2),
        untouched=("system/setCardiacAnatomyDict", ("zApicalMid",)),
        sweep_name="system/setPurkinjeSlabDict:multiplier",
        sweep_values=(2.0, 4.0),
        unknown_name="system/setPurkinjeSlabDict:thicknes",
        # Real utilities over a real anatomy bundle; generous but bounded.
        timeout_s=900.0,
    ),
    "idealizedHeart": dict(requires=_HUMAN_SLAB_UTILITIES, **_IDEALIZED),
    "idealizedHeartEndocardial": dict(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "generatePurkinjeTree"), **_IDEALIZED,
    ),
    "idealizedHeartPigTransmural": dict(
        requires=("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeMorphometry", "generatePurkinjeTree"),
        **_IDEALIZED,
    ),
}


def conformance_target(record: str, tmp_path: Path) -> ConformanceTarget:
    row = dict(TARGETS[record])
    require_commands(*row.pop("requires"))
    inputs = {"anatomy": str(native_cardiaccore_anatomy())} if record == "humanSlab" else {}
    return ConformanceTarget(
        plugin="cardiaccore", record=record, cases_root=native_cardiaccore_tree(),
        scratch_root=tmp_path / "scratch", inputs=inputs, **row,
    )
