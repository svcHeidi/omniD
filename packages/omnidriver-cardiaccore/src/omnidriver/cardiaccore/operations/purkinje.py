"""Array methods for cardiacCore seed proposals and coverage observations.

Native dictionaries remain the execution truth. Method constants and the
named baseline policy are declared once in catalogs.purkinje; this module
implements observations without judging scientific acceptance. Only the
explicit write_seed_dictionary entrypoint mutates a supplied case dictionary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
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


def _read_pyvista_scalar(mesh: Any, name: str, path: Path) -> np.ndarray:
    """Read one scalar from native VTK point data or convert cell data."""
    if name in mesh.point_data:
        values = np.asarray(mesh.point_data[name])
    elif name in mesh.cell_data:
        values = np.asarray(mesh.cell_data_to_point_data()[name])
    else:
        raise ValueError(f"{path} is missing native VTK field {name!r}")
    if len(values) != mesh.n_points:
        raise ValueError(f"{path}: native VTK field {name!r} is not point-aligned")
    return values


def read_native_seed_surface_fields(
    lv_surface: Path,
    rv_surface: Path,
) -> dict[str, np.ndarray]:
    """Read the two native endocardial surface exports for seed deduction.

    ``lv_surface`` and ``rv_surface`` are the explicit ``foamToVTK`` exports
    of the generator's ``LVEndoFaces`` and ``RVEndoFaces`` sets. The returned
    arrays are aligned and can be passed directly to :func:`deduce_seeds`.
    No UVC threshold is re-derived here: the native generator has already
    selected the growable surfaces.
    """
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ValueError(
            "native VTK seed-surface reading requires omnidriver-cardiaccore[vtk]"
        ) from exc

    lv = pv.read(str(lv_surface))
    rv = pv.read(str(rv_surface))
    for mesh, path in ((lv, lv_surface), (rv, rv_surface)):
        if mesh.n_points == 0:
            raise ValueError(f"{path}: native VTK surface has no points")

    return {
        "points": np.concatenate((np.asarray(lv.points), np.asarray(rv.points))),
        "aha_segment": np.concatenate((
            _read_pyvista_scalar(lv, "AHA_Segment", lv_surface),
            _read_pyvista_scalar(rv, "AHA_Segment", rv_surface),
        )),
        "uvc_longitudinal": np.concatenate((
            _read_pyvista_scalar(lv, "uvc_longitudinal", lv_surface),
            _read_pyvista_scalar(rv, "uvc_longitudinal", rv_surface),
        )),
        "lv_endocardial_mask": np.concatenate((
            np.ones(lv.n_points, dtype=bool),
            np.zeros(rv.n_points, dtype=bool),
        )),
        "rv_endocardial_mask": np.concatenate((
            np.zeros(lv.n_points, dtype=bool),
            np.ones(rv.n_points, dtype=bool),
        )),
    }


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


_SEED_DICTIONARY_ENTRIES = {
    "his_bundle_seed": (None, "hisBundleSeed"),
    "lv_seed": ("lv", "seed"),
    "lv_line_end": ("lv", "lineEnd"),
    "rv_seed": ("rv", "seed"),
    "rv_line_end": ("rv", "lineEnd"),
}


def _seed_vector(value: Any, name: str) -> tuple[float, float, float]:
    try:
        vector = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite length-3 coordinate") from exc
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite length-3 coordinate")
    return tuple(float(component) for component in vector)


def write_seed_dictionary(
    dictionary: Path,
    proposal: Mapping[str, Any],
) -> None:
    """Write a reviewed seed proposal into an existing native tree dictionary.

    The native generator reads these exact top-level and ventricular keys. The
    writer accepts the complete proposal produced by :func:`deduce_seeds`,
    updates existing entries only, and leaves native growth and terminal
    defaults untouched. Callers must stage the case before invoking it.
    """
    expected = set(_SEED_DICTIONARY_ENTRIES)
    received = set(proposal)
    if received != expected:
        missing = ", ".join(sorted(expected - received))
        extra = ", ".join(sorted(received - expected))
        details = []
        if missing:
            details.append(f"missing {missing}")
        if extra:
            details.append(f"unexpected {extra}")
        raise ValueError(
            "seed proposal must contain exactly the reviewed entries ("
            + "; ".join(details)
            + ")"
        )

    vectors = {
        name: _seed_vector(value, name)
        for name, value in proposal.items()
    }
    for vent in ("lv", "rv"):
        if np.linalg.norm(
            np.asarray(vectors[f"{vent}_line_end"])
            - np.asarray(vectors[f"{vent}_seed"])
        ) < 1e-12:
            raise ValueError(f"{vent}.lineEnd must differ from {vent}.seed")

    from omnidriver.openfoam.mutators import read_foam_entry, update_foam_entry

    # Preflight every entry so a malformed native dictionary cannot receive
    # only a partial proposal.
    for name, (scope, key) in _SEED_DICTIONARY_ENTRIES.items():
        if read_foam_entry(dictionary, key, scope=scope) is None:
            location = key if scope is None else f"{scope}.{key}"
            raise ValueError(f"{dictionary}: missing existing seed entry {location}")

    for name, (scope, key) in _SEED_DICTIONARY_ENTRIES.items():
        value = "(" + " ".join(str(component) for component in vectors[name]) + ")"
        update_foam_entry(dictionary, key, value, scope=scope)


def seed_area_placement_report(
    proposal: Mapping[str, Any],
    fields: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Record whether proposed roots occupy the declared native seed areas.

    The report is intentionally a placement receipt, not a scientific
    acceptance result.  It checks the two roots against the native points
    actually labelled as the method's LV/RV basal-septal candidate areas and
    records whether the His point is their midpoint.  Line ends are
    intentionally not required to coincide with a surface sample: the method
    derives an apex-ward direction from the local longitudinal gradient.
    """
    expected = set(_SEED_DICTIONARY_ENTRIES)
    if set(proposal) != expected:
        raise ValueError("seed proposal must contain exactly the reviewed entries")
    required_fields = {
        "points", "aha_segment", "lv_endocardial_mask", "rv_endocardial_mask",
    }
    missing = required_fields.difference(fields)
    if missing:
        raise ValueError("seed-area fields are missing " + ", ".join(sorted(missing)))
    points = np.asarray(fields["points"], dtype=float)
    aha = np.rint(np.asarray(fields["aha_segment"])).astype(int)
    lv_mask = np.asarray(fields["lv_endocardial_mask"], dtype=bool)
    rv_mask = np.asarray(fields["rv_endocardial_mask"], dtype=bool)
    if points.ndim != 2 or points.shape[1] != 3 or not all(
        len(values) == len(points) for values in (aha, lv_mask, rv_mask)
    ):
        raise ValueError("seed-area fields must align to finite Nx3 surface points")
    if not np.all(np.isfinite(points)):
        raise ValueError("seed-area points must be finite")

    lv_candidates = points[lv_mask & np.isin(aha, LV_SEPTAL_AHA_SEGMENTS)]
    rv_candidates = points[rv_mask & (aha == RV_BASAL_SEPTAL_AHA_SEGMENT)]
    if not len(lv_candidates) or not len(rv_candidates):
        raise ValueError("native surface exports do not contain both declared seed areas")

    lv_seed = np.asarray(_seed_vector(proposal["lv_seed"], "lv_seed"))
    rv_seed = np.asarray(_seed_vector(proposal["rv_seed"], "rv_seed"))
    his_seed = np.asarray(_seed_vector(proposal["his_bundle_seed"], "his_bundle_seed"))
    return {
        "lv": {
            "surface": "LVEndoFaces",
            "aha_segments": LV_SEPTAL_AHA_SEGMENTS,
            "candidate_count": int(len(lv_candidates)),
            "seed_is_native_candidate": bool(np.any(np.all(lv_candidates == lv_seed, axis=1))),
        },
        "rv": {
            "surface": "RVEndoFaces",
            "aha_segments": (RV_BASAL_SEPTAL_AHA_SEGMENT,),
            "candidate_count": int(len(rv_candidates)),
            "seed_is_native_candidate": bool(np.any(np.all(rv_candidates == rv_seed, axis=1))),
        },
        "his_bundle": {
            "is_midpoint_of_roots": bool(np.array_equal(his_seed, (lv_seed + rv_seed) / 2.0)),
        },
    }


def deduce_and_write_native_seed_dictionary(
    lv_surface: Path,
    rv_surface: Path,
    dictionary: Path,
) -> dict[str, Any]:
    """Bridge supplied native surface exports to one staged tree dictionary.

    This is deliberately not an automatic tree workflow.  The native utility
    has no surface-preparation-only command: callers export the relevant
    ``LVEndoFaces``/``RVEndoFaces`` from an explicitly selected prior run,
    then pass the staged ``generatePurkinjeTreeDict`` to this function before
    their next tree execution.
    """
    fields = read_native_seed_surface_fields(lv_surface, rv_surface)
    proposal = deduce_seeds(**fields)
    placement = seed_area_placement_report(proposal, fields)
    if not (
        placement["lv"]["seed_is_native_candidate"]
        and placement["rv"]["seed_is_native_candidate"]
        and placement["his_bundle"]["is_midpoint_of_roots"]
    ):
        raise RuntimeError("deduced native seed proposal failed its placement receipt")
    write_seed_dictionary(dictionary, proposal)
    return {"proposal": proposal, "placement": placement}
