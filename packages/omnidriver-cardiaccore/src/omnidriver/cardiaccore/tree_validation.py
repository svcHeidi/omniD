"""Canonical anatomy-aware validation contract for cardiacCore trees.

This is the adapter-owned representation that OmniD agents use.  The native
generator and its dictionaries remain the execution truth; historical
standalone scripts and notes are evidence for this normalized contract, not
additional instructions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np


# The normal AHA-17 LV basal-septal sectors.  The generator's recovered RV
# septal wall does not carry a stable RV AHA code, so its contract is UVC-based.
LV_SEPTAL_AHA_SEGMENTS = (2, 3)
LV_TRANSMURAL_MAX = 0.15
RV_SEPTAL_TRANSMURAL_MIN = 0.9
RV_LONGITUDINAL_RANGE = (0.6, 0.8)
APICAL_STEP_NEIGHBOURS = 24

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

_REQUIRED_BASELINE_SEGMENTS = frozenset(range(7, 18)) | frozenset(range(22, 30))
_BASAL_REFERENCE_SEGMENTS = frozenset(range(1, 7)) | frozenset(range(18, 22))

TREE_VALIDATION_CONTRACT: dict[str, Any] = {
    "seed_placement": {
        "lv": {
            "anatomy": "basal LV septal endocardium",
            "aha_segments": LV_SEPTAL_AHA_SEGMENTS,
            "uvc_intraventricular": "< 0",
            "uvc_transmural": f"<= {LV_TRANSMURAL_MAX}",
        },
        "rv": {
            "anatomy": "generator-recovered RV septal endocardium",
            "aha_segments": None,
            "uvc_intraventricular": "< 0 (LV-inherited recovered-septum convention)",
            "uvc_transmural": f">= {RV_SEPTAL_TRANSMURAL_MIN}",
            "uvc_longitudinal": f"{RV_LONGITUDINAL_RANGE[0]} < value < {RV_LONGITUDINAL_RANGE[1]}",
        },
        "his_bundle": "midpoint of the LV and RV roots",
        "line_end": "local apex-ward direction inferred from uvc_longitudinal",
    },
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


def _nearest_point(points: np.ndarray, mask: np.ndarray, target: np.ndarray) -> np.ndarray:
    candidates = points[mask]
    return candidates[np.argmin(np.linalg.norm(candidates - target, axis=1))]


def _apical_line_end(
    points: np.ndarray,
    longitudinal: np.ndarray,
    surface_mask: np.ndarray,
    seed: np.ndarray,
) -> np.ndarray:
    candidates = points[surface_mask]
    candidate_longitudinal = longitudinal[surface_mask]
    distances = np.linalg.norm(candidates - seed, axis=1)
    count = min(APICAL_STEP_NEIGHBOURS, len(distances))
    indices = np.argsort(distances)[:count]
    design = np.column_stack([candidates[indices], np.ones(count)])
    coefficients, *_ = np.linalg.lstsq(design, candidate_longitudinal[indices], rcond=None)
    gradient = coefficients[:3]
    norm = np.linalg.norm(gradient)
    if norm < 1e-12:
        raise ValueError("uvc_longitudinal has no local gradient near the seed")
    nonzero = distances[indices][distances[indices] > 0]
    step = np.median(nonzero) if nonzero.size else 1.0
    return seed - step * gradient / norm


def deduce_seeds(
    points: np.ndarray,
    aha_segment: np.ndarray,
    uvc_transmural: np.ndarray,
    uvc_intraventricular: np.ndarray,
    uvc_longitudinal: np.ndarray,
) -> dict[str, tuple[float, float, float]]:
    """Deduce anatomy-portable LV/RV/His roots and apex-ward line ends.

    Inputs are genuine boundary-surface points with fields sampled on the same
    mesh the generator will use.  This routine deliberately never writes a
    dictionary; callers compare its result to a requested fixed dictionary.
    """
    points = np.asarray(points, dtype=float)
    aha_segment = np.rint(np.asarray(aha_segment)).astype(int)
    transmural = np.asarray(uvc_transmural, dtype=float)
    intraventricular = np.asarray(uvc_intraventricular, dtype=float)
    longitudinal = np.asarray(uvc_longitudinal, dtype=float)

    if not all(len(values) == len(points) for values in (
        aha_segment, transmural, intraventricular, longitudinal,
    )):
        raise ValueError("seed-deduction fields must have one value per surface point")

    lv_mask = intraventricular < 0.0
    lv_septal = (
        lv_mask
        & np.isin(aha_segment, LV_SEPTAL_AHA_SEGMENTS)
        & (transmural <= LV_TRANSMURAL_MAX)
    )
    if not np.any(lv_septal):
        raise ValueError("no LV candidate matches basal-septal AHA segments {2,3}")
    lv_seed = _nearest_point(points, lv_mask, points[lv_septal].mean(axis=0))

    rv_septal = (
        lv_mask
        & (transmural >= RV_SEPTAL_TRANSMURAL_MIN)
        & (longitudinal > RV_LONGITUDINAL_RANGE[0])
        & (longitudinal < RV_LONGITUDINAL_RANGE[1])
    )
    if not np.any(rv_septal):
        raise ValueError("no candidate matches the recovered-RV-septal UVC criterion")
    rv_seed = _nearest_point(points, rv_septal, lv_seed)
    his_bundle_seed = (lv_seed + rv_seed) / 2.0

    return {
        "lv_seed": tuple(float(value) for value in lv_seed),
        "lv_line_end": tuple(float(value) for value in _apical_line_end(
            points, longitudinal, lv_mask, lv_seed,
        )),
        "rv_seed": tuple(float(value) for value in rv_seed),
        "rv_line_end": tuple(float(value) for value in _apical_line_end(
            points, longitudinal, rv_septal, rv_seed,
        )),
        "his_bundle_seed": tuple(float(value) for value in his_bundle_seed),
    }


def coverage_report(
    terminal_aha_segment: np.ndarray,
    endocardial_aha_segment: np.ndarray | None = None,
) -> dict[str, Any]:
    """Report AHA terminal occupancy without asserting a density threshold."""
    terminal_ids = np.rint(np.asarray(terminal_aha_segment)).astype(int)
    counts = Counter(terminal_ids.tolist())
    endocardial_ids = (
        None
        if endocardial_aha_segment is None
        else set(np.rint(np.asarray(endocardial_aha_segment)).astype(int).tolist())
    )

    all_names = {**LV_AHA_NAMES, **RV_AHA_NAMES}
    segment_counts = {segment: counts.get(segment, 0) for segment in all_names}
    no_endocardium = (
        set() if endocardial_ids is None
        else {segment for segment in all_names if segment not in endocardial_ids}
    )
    starved = {
        segment for segment, count in segment_counts.items()
        if count == 0 and segment not in no_endocardium
    }
    required_missing = tuple(sorted(starved & _REQUIRED_BASELINE_SEGMENTS))
    basal_warnings = tuple(sorted(starved & _BASAL_REFERENCE_SEGMENTS))

    return {
        "counts": segment_counts,
        "starved": tuple(sorted(starved)),
        "no_endocardium": tuple(sorted(no_endocardium)),
        "required_missing": required_missing,
        "basal_warnings": basal_warnings,
        "lv_total": sum(segment_counts[segment] for segment in LV_AHA_NAMES),
        "rv_total": sum(segment_counts[segment] for segment in RV_AHA_NAMES),
        "unrecognized_segment_ids": tuple(sorted(set(counts) - set(all_names))),
    }
