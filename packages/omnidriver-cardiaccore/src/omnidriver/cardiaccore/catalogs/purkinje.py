"""Declared method constants and coverage policy; no analysis is run here.

Purkinje seed placement is not declared here: it lives in
cardiacCoreStandalone's own scripts/place_purkinje_seeds.py. An earlier
AHA-segment-based seed-candidate declaration (LV_SEPTAL_AHA_SEGMENTS,
RV_BASAL_SEPTAL_AHA_SEGMENT, APICAL_STEP_NEIGHBOURS, and
TREE_VALIDATION_CONTRACT's seed_placement key) was removed 2026-09-23 at
the user's explicit instruction, after that method was tried and rejected
in cardiacCoreStandalone. Do not reintroduce it.
"""

from typing import Any

LV_SEPTAL_TO_RV_SEPTAL_CODE = {2: 21, 3: 21, 8: 25, 9: 25, 14: 29}

LV_AHA_NAMES = {
    1: "Basal Anterior",
    2: "Basal Anteroseptal",
    3: "Basal Inferoseptal",
    4: "Basal Inferior",
    5: "Basal Inferolateral",
    6: "Basal Anterolateral",
    7: "Mid Anterior",
    8: "Mid Anteroseptal",
    9: "Mid Inferoseptal",
    10: "Mid Inferior",
    11: "Mid Inferolateral",
    12: "Mid Anterolateral",
    13: "Apical Anterior",
    14: "Apical Septal",
    15: "Apical Inferior",
    16: "Apical Lateral",
    17: "Apex",
}
RV_AHA_NAMES = {
    18: "Basal Sector A",
    19: "Basal Sector B",
    20: "Basal Sector C",
    21: "Basal Septal",
    22: "Mid Sector A",
    23: "Mid Sector B",
    24: "Mid Sector C",
    25: "Mid Septal",
    26: "Apical Sector A",
    27: "Apical Sector B",
    28: "Apical Sector C",
    29: "Apical Septal",
}

REQUIRED_BASELINE_SEGMENTS = frozenset(range(7, 18)) | frozenset(range(22, 30))
BASAL_REFERENCE_SEGMENTS = frozenset(range(1, 7)) | frozenset(range(18, 22))

TREE_VALIDATION_CONTRACT: dict[str, Any] = {
    "id": "cardiaccore.purkinje.baseline.v1",
    "version": 1,
    "scope": "Preserved adapter method assumptions and coverage categories; not universal scientific acceptance.",
    "baseline_coverage": {
        "required_if_endocardium_exists": {
            "lv": tuple(range(7, 18)),
            "rv": tuple(range(22, 30)),
        },
        "warning_only": {
            "lv": tuple(range(1, 7)),
            "rv": tuple(range(18, 22)),
        },
        "node_or_terminal_count": "recorded reference observation only; no global threshold",
        "surface_distance": "record for later ECG-driven optimisation; no global pass threshold",
    },
}
