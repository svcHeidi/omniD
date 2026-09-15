"""Array methods for cardiacCore seed proposals and coverage observations.

Native dictionaries remain the execution truth. Method constants and the
named baseline policy are declared once in catalogs.purkinje; this module
implements them without writing a case or judging scientific acceptance.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from ..catalogs.purkinje import (
    APICAL_STEP_NEIGHBOURS, LV_AHA_NAMES, LV_SEPTAL_AHA_SEGMENTS,
    LV_SEPTAL_TO_RV_SEPTAL_CODE, RV_AHA_NAMES, RV_BASAL_SEPTAL_AHA_SEGMENT,
    REQUIRED_BASELINE_SEGMENTS, BASAL_REFERENCE_SEGMENTS,
)


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
    uvc_longitudinal: np.ndarray,
    lv_endocardial_mask: np.ndarray,
    rv_endocardial_mask: np.ndarray,
) -> dict[str, tuple[float, float, float]]:
    """Deduce anatomy-portable LV/RV/His roots and apex-ward line ends.

    The masks must come from the generator's ``LVEndoFaces`` and
    ``RVEndoFaces`` outputs, sampled on the same surface-point set. This
    routine deliberately never writes a dictionary; callers compare its
    result to a requested fixed dictionary.
    """
    points = np.asarray(points, dtype=float)
    aha_segment = np.rint(np.asarray(aha_segment)).astype(int)
    longitudinal = np.asarray(uvc_longitudinal, dtype=float)
    lv_surface = np.asarray(lv_endocardial_mask, dtype=bool)
    rv_surface = np.asarray(rv_endocardial_mask, dtype=bool)

    if not all(len(values) == len(points) for values in (
        aha_segment, longitudinal, lv_surface, rv_surface,
    )):
        raise ValueError("seed-deduction fields must have one value per surface point")

    lv_septal = lv_surface & np.isin(aha_segment, LV_SEPTAL_AHA_SEGMENTS)
    if not np.any(lv_septal):
        raise ValueError("no LVEndoFaces candidate matches basal-septal AHA segments {2,3}")
    lv_seed = _nearest_point(points, lv_surface, points[lv_septal].mean(axis=0))

    rv_septal = rv_surface & (aha_segment == RV_BASAL_SEPTAL_AHA_SEGMENT)
    if not np.any(rv_septal):
        raise ValueError("no RVEndoFaces candidate matches basal-septal AHA segment 21")
    rv_seed = _nearest_point(points, rv_septal, lv_seed)
    his_bundle_seed = (lv_seed + rv_seed) / 2.0

    return {
        "lv_seed": tuple(float(value) for value in lv_seed),
        "lv_line_end": tuple(float(value) for value in _apical_line_end(
            points, longitudinal, lv_surface, lv_seed,
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
    terminal_tree_zone: np.ndarray | None = None,
) -> dict[str, Any]:
    """Report AHA terminal occupancy without asserting a density threshold."""
    terminal_ids = normalize_rv_septal_segments(
        terminal_aha_segment, terminal_tree_zone
    )
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
    required_missing = tuple(sorted(starved & REQUIRED_BASELINE_SEGMENTS))
    basal_warnings = tuple(sorted(starved & BASAL_REFERENCE_SEGMENTS))

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


def normalize_rv_septal_segments(
    aha_segment: np.ndarray, tree_zone: np.ndarray | None = None,
) -> np.ndarray:
    """Credit RV-tree terminals on recovered septum to RV AHA segments.

    ``CellZone == 2`` is emitted by the native generator for the RV tree.
    Only those samples are remapped, so LV-tree terminals on the same physical
    septum retain their valid LV labels.
    """
    ids = np.rint(np.asarray(aha_segment)).astype(int).copy()
    if tree_zone is None:
        return ids
    zones = np.asarray(tree_zone)
    if len(zones) != len(ids):
        raise ValueError("terminal tree-zone values must align with terminal AHA segments")
    rv_tree = zones == 2
    for lv_code, rv_code in LV_SEPTAL_TO_RV_SEPTAL_CODE.items():
        ids[rv_tree & (ids == lv_code)] = rv_code
    return ids
