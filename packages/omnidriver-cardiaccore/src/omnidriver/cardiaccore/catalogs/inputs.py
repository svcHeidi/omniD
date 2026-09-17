"""Evidence-labelled input catalog for the initial cardiacCore workflow.

Only settings present in the selected native ``bivCase`` dictionaries are
published as reviewed ``DictEntry`` values.  Branches with an established
workflow role remain in ``CONDITIONAL_INPUTS`` until that workflow is selected.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog


_CONDUCTIVITY_SOURCE = "src/setCardiacConductivity/setCardiacConductivity.C"
_ANATOMY_SOURCE = "src/setCardiacAnatomy/setCardiacAnatomy.C"
_SLAB_SOURCE = "src/setPurkinjeSlab/setPurkinjeSlab.C"
_MORPHOMETRY_SOURCE = "src/setPurkinjeMorphometry/setPurkinjeMorphometry.C"


CONDUCTIVITY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.df",
        description="Longitudinal conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.ds",
        description="Sheet-direction conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.dn",
        description="Normal-direction conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.fiberField",
        description="Name of the vector field defining the fibre direction.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        value_kind="word",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.sheetField",
        description="Name of the vector field defining the sheet direction.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        value_kind="word",
        required=True,
    ),
)

ANATOMY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zApicalMid",
        description="Longitudinal UVC threshold separating apical and mid AHA regions.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zMidBasal",
        description="Longitudinal UVC threshold separating mid and basal AHA regions.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zApexCap",
        description="Longitudinal UVC extent assigned to the apical cap.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
)

SLAB_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$PURKINJE_SLAB.thickness",
        description="Sub-endocardial slab thickness in the case's transmural-coordinate units.",
        source_refs=("cases/bivCase/system/setPurkinjeSlabDict", _SLAB_SOURCE),
        value_kind="scalar",
        constraints=("Must lie between zero and the configured transmural-coordinate range.",),
        # This utility is optional at the adapter level: a selected workflow
        # must read this dictionary before it becomes a required case input.
        required=False,
    ),
    DictEntry(
        driver_path="$PURKINJE_SLAB.multiplier",
        description="Conductivity multiplier applied within the Purkinje slab.",
        source_refs=("cases/bivCase/system/setPurkinjeSlabDict", _SLAB_SOURCE),
        value_kind="scalar",
        required=False,
    ),
)

# setPurkinjeMorphometryDict currently has no reviewed, driver-overridable
# x-values: groove detection is unconditional native behaviour (never a
# dictionary input), and its one remaining source-defined value
# (subendocardialWeight) is published only as a conditional input below,
# not as a strict-validated DictEntry.
MORPHOMETRY_ENTRIES: Final[tuple[DictEntry, ...]] = ()

_RAW_DOCUMENTS: Final[dict[str, tuple[DictEntry, ...]]] = {
    "setCardiacConductivityDict": CONDUCTIVITY_ENTRIES,
    "setCardiacAnatomyDict": ANATOMY_ENTRIES,
    "setPurkinjeSlabDict": SLAB_ENTRIES,
    "setPurkinjeMorphometryDict": MORPHOMETRY_ENTRIES,
}

# These values are all consumed before a cardiac solver exists in this
# workflow. Giving them one adapter-owned phase makes strict validation honest
# without borrowing cardiacFoam's anatomy/physics/stimulus/solver vocabulary.
DOCUMENTS: Final[dict[str, tuple[DictEntry, ...]]] = {
    name: tuple(replace(entry, phases=frozenset({"preprocessing"})) for entry in entries)
    for name, entries in _RAW_DOCUMENTS.items()
}

CATALOG: Final[DictionaryCatalog] = DictionaryCatalog(DOCUMENTS)

# These are real source reads but are not present in the selected auto-mode
# bivCase.  Their workflow roles were supplied by the domain owner; they are
# visible without becoming mutable x values for the current vertical slice.
CONDITIONAL_INPUTS: Final[dict[str, tuple[dict[str, object], ...]]] = {
    "setCardiacConductivityDict": (
        {
            "path": "conductivityIntracellular.{df,ds,dn}",
            "status": "conditional",
            "value_kind": "scalar",
            "when": "bidomain tensor preprocessing is selected",
            "reason": (
                "Used only when both paired bidomain subdictionaries are present."
            ),
            "evidence": [_CONDUCTIVITY_SOURCE],
        },
        {
            "path": "conductivityExtracellular.{df,ds,dn}",
            "status": "conditional",
            "value_kind": "scalar",
            "when": "bidomain tensor preprocessing is selected",
            "reason": (
                "Used only when both paired bidomain subdictionaries are present."
            ),
            "evidence": [_CONDUCTIVITY_SOURCE],
        },
    ),
    "setPurkinjeMorphometryDict": (
        {
            "path": "subendocardialWeight",
            "status": "conditional",
            "value_kind": "scalar",
            "when": "the pig Purkinje morphometry algorithm is selected",
            "reason": (
                "Source-defined optional value; bivCase uses the compiled default 0.56."
            ),
            "evidence": [_MORPHOMETRY_SOURCE],
        },
    ),
}
