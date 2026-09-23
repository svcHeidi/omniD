"""Array methods for cardiacCore coverage observations.

Native dictionaries remain the execution truth. Method constants and the
named baseline policy are declared once in catalogs.purkinje; this module
implements observations without judging scientific acceptance.

Purkinje seed placement is NOT done here: it lives entirely in
cardiacCoreStandalone's own scripts/place_purkinje_seeds.py (septal-midline
method via aha_angle=0), not in this package. An earlier AHA-segment-based
seed-deduction implementation (deduce_seeds, write_seed_dictionary,
read_seed_dictionary, seed_area_placement_report,
deduce_and_write_native_seed_dictionary, and the
cardiaccore.purkinje.seed_proposal.v1 catalog entry) was removed 2026-09-23
at the user's explicit instruction, after it was tried and rejected as a
Purkinje seed-candidate method in cardiacCoreStandalone (AHA_Segment's
~20-30deg wedges extend well past the true septal wall). Do not reintroduce
seed-placement logic in this package.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from ..catalogs.purkinje import (
    LV_AHA_NAMES, LV_SEPTAL_TO_RV_SEPTAL_CODE, RV_AHA_NAMES,
    REQUIRED_BASELINE_SEGMENTS, BASAL_REFERENCE_SEGMENTS,
)


def _native_tree_point_zones(tree: Any, path: Path) -> np.ndarray | None:
    if "CellZone" not in tree.cell_data:
        return None
    zones = np.asarray(tree.cell_data["CellZone"])
    lines = np.asarray(tree.lines, dtype=int)
    point_zones = np.full(tree.n_points, -1, dtype=int)
    offset = 0
    line_count = 0
    while offset < len(lines):
        count = int(lines[offset])
        if count < 2 or offset + count >= len(lines):
            raise ValueError(f"{path}: malformed VTK line connectivity")
        if line_count >= len(zones):
            raise ValueError(f"{path}: CellZone data is not line-aligned")
        for point_id in lines[offset + 1:offset + count + 1]:
            if point_id < 0 or point_id >= tree.n_points:
                raise ValueError(f"{path}: line references an invalid point")
            if point_zones[point_id] == -1:
                point_zones[point_id] = int(round(float(zones[line_count])))
        offset += count + 1
        line_count += 1
    if line_count != len(zones):
        raise ValueError(f"{path}: CellZone data is not line-aligned")
    return point_zones


def coverage_report_from_native_files(
    purkinje_vtk: Path,
    volume_vtu: Path,
    lv_endo_faceset_vtp: Path | None = None,
    rv_endo_faceset_vtp: Path | None = None,
) -> dict[str, Any]:
    """Sample native tree/field exports and return the baseline coverage report.

    ``volume_vtu`` is the internal ``foamToVTK`` export carrying cell data
    ``AHA_Segment``. Optional face-set exports distinguish an absent
    endocardial sector from a sector the tree failed to reach. This performs
    only geometric nearest-cell sampling and the named baseline observation;
    it does not claim scientific acceptance.
    """
    if (lv_endo_faceset_vtp is None) != (rv_endo_faceset_vtp is None):
        raise ValueError("LVEndoFaces and RVEndoFaces exports must be supplied together")
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ValueError(
            "native VTK coverage reading requires omnidriver-cardiaccore[vtk]"
        ) from exc

    tree = pv.read(str(purkinje_vtk))
    volume = pv.read(str(volume_vtu))
    if "NodeType" not in tree.point_data:
        raise ValueError(f"{purkinje_vtk} has no NodeType point data")
    if "AHA_Segment" not in volume.cell_data:
        raise ValueError(f"{volume_vtu} has no AHA_Segment cell data")

    terminal_mask = np.rint(np.asarray(tree.point_data["NodeType"])).astype(int) == 2
    terminal_points = np.asarray(tree.points)[terminal_mask]
    terminal_cells = np.atleast_1d(volume.find_closest_cell(terminal_points))
    terminal_aha = np.rint(
        np.asarray(volume.cell_data["AHA_Segment"])[terminal_cells]
    ).astype(int)
    terminal_zones = _native_tree_point_zones(tree, purkinje_vtk)
    terminal_zone_values = None if terminal_zones is None else terminal_zones[terminal_mask]

    endocardial_aha = None
    if lv_endo_faceset_vtp is not None:
        lv_surface = pv.read(str(lv_endo_faceset_vtp))
        rv_surface = pv.read(str(rv_endo_faceset_vtp))
        for surface, path in (
            (lv_surface, lv_endo_faceset_vtp),
            (rv_surface, rv_endo_faceset_vtp),
        ):
            if surface.n_cells == 0:
                raise ValueError(f"{path}: native endocardial surface has no cells")
        lv_points = np.asarray(lv_surface.cell_centers().points)
        rv_points = np.asarray(rv_surface.cell_centers().points)
        lv_cells = np.atleast_1d(volume.find_closest_cell(lv_points))
        rv_cells = np.atleast_1d(volume.find_closest_cell(rv_points))
        lv_aha = np.rint(
            np.asarray(volume.cell_data["AHA_Segment"])[lv_cells]
        ).astype(int)
        rv_aha = np.rint(
            np.asarray(volume.cell_data["AHA_Segment"])[rv_cells]
        ).astype(int)
        # RVEndoFaces includes the native septal-recovery band.  Its samples
        # can retain LV septal AHA labels, so remap only this surface as RV;
        # applying the terminal remapper to the concatenated labels without
        # zones would leave every value unchanged.
        rv_aha = normalize_rv_septal_segments(
            rv_aha, np.full(len(rv_aha), 2, dtype=int)
        )
        endocardial_aha = np.concatenate((lv_aha, rv_aha))

    return coverage_report(terminal_aha, endocardial_aha, terminal_zone_values)


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

