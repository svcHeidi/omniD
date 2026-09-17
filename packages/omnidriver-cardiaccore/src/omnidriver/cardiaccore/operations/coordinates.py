"""Coordinate-convention discovery and geometry prerequisites.

These read-only checks precede anatomy and Purkinje work.  They establish
which supported coordinate field triplet is present, then use the declared
intraventricular, longitudinal, and transmural values to test endocardial-ring
topology.  They neither construct native face sets nor change a coordinate
field or a native dictionary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_BASAL_RING_LEVELS = np.asarray((0.1, 0.4), dtype=float)
_BASAL_RING_SPACING_FRACTION = 0.3
_MAX_SEAM_POINT_FRACTION = 0.02


def _fixed_basal_ring_levels(ring_levels: Any) -> np.ndarray:
    levels = np.asarray(ring_levels, dtype=float)
    if levels.shape != _BASAL_RING_LEVELS.shape or not np.allclose(
        levels, _BASAL_RING_LEVELS, rtol=0.0, atol=1e-12,
    ):
        raise ValueError("ring_levels is fixed to basal levels (0.1, 0.4)")
    return levels


def _pyvista():
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ValueError(
            "coordinate validation requires omnidriver-cardiaccore[vtk]"
        ) from exc
    return pv


def _mesh_point_scalar(mesh: Any, name: str, path: Path) -> np.ndarray:
    if name in mesh.point_data:
        values = np.asarray(mesh.point_data[name])
    elif name in mesh.cell_data:
        converted = mesh.cell_data_to_point_data()
        if name not in converted.point_data:
            raise ValueError(f"{path}: coordinate field {name!r} cannot be point-sampled")
        values = np.asarray(converted.point_data[name])
    else:
        raise ValueError(f"{path} is missing coordinate field {name!r}")
    if values.ndim != 1 or len(values) != mesh.n_points or not np.all(np.isfinite(values)):
        raise ValueError(f"{path}: coordinate field {name!r} must be finite point scalars")
    return values


def _mesh_cell_scalar(mesh: Any, name: str, path: Path) -> np.ndarray:
    if name in mesh.cell_data:
        values = np.asarray(mesh.cell_data[name])
    elif name in mesh.point_data:
        values = np.asarray(mesh.point_data_to_cell_data()[name])
    else:
        raise ValueError(f"{path} is missing coordinate field {name!r}")
    if values.ndim != 1 or len(values) != mesh.n_cells or not np.all(np.isfinite(values)):
        raise ValueError(f"{path}: coordinate field {name!r} must be finite cell scalars")
    return values


def _binary_chamber_with_seam(
    values: np.ndarray,
    first_value: float,
    second_value: float,
    binary_tolerance: float,
    seam_point_fraction_tolerance: float,
) -> tuple[bool, int, float]:
    """Allow a small cell-to-point-interpolated seam between two endpoints."""
    lower, upper = sorted((first_value, second_value))
    within_chamber_interval = (values >= lower - binary_tolerance) & (
        values <= upper + binary_tolerance
    )
    endpoint = np.isclose(values, first_value, atol=binary_tolerance) | np.isclose(
        values, second_value, atol=binary_tolerance,
    )
    seam = within_chamber_interval & ~endpoint
    seam_count = int(np.count_nonzero(seam))
    seam_fraction = seam_count / len(values)
    accepted = bool(
        np.all(within_chamber_interval)
        and np.any(np.isclose(values, first_value, atol=binary_tolerance))
        and np.any(np.isclose(values, second_value, atol=binary_tolerance))
        and seam_fraction <= seam_point_fraction_tolerance
    )
    return accepted, seam_count, seam_fraction


def _contour_components(contour: Any) -> tuple[tuple[np.ndarray, bool], ...]:
    """Return connected contour components and whether each one is closed."""
    lines = np.asarray(contour.lines, dtype=int)
    edges: list[tuple[int, int]] = []
    offset = 0
    while offset < len(lines):
        count = int(lines[offset])
        if count < 2 or offset + count >= len(lines):
            raise ValueError("contour output has malformed line connectivity")
        ids = lines[offset + 1:offset + count + 1]
        edges.extend((int(left), int(right)) for left, right in zip(ids[:-1], ids[1:]))
        offset += count + 1
    if not edges:
        return tuple()

    adjacency: dict[int, set[int]] = {}
    for left, right in edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    remaining = set(adjacency)
    components = []
    while remaining:
        stack = [remaining.pop()]
        component: set[int] = set()
        while stack:
            point_id = stack.pop()
            component.add(point_id)
            for neighbour in adjacency[point_id]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
        components.append((
            np.asarray(sorted(component), dtype=int),
            all(len(adjacency[point_id]) == 2 for point_id in component),
        ))
    return tuple(components)


def _minimum_point_distance(points: np.ndarray, reference: np.ndarray) -> float:
    """Avoid allocating a full contour-by-reference distance matrix."""
    minimum = float("inf")
    for chunk_start in range(0, len(points), 256):
        distances = np.linalg.norm(
            points[chunk_start:chunk_start + 256, None, :] - reference[None, :, :],
            axis=2,
        )
        minimum = min(minimum, float(np.min(distances)))
    return minimum


def _largest_ab_zero_reference(selected_surface: Any) -> tuple[np.ndarray, dict[str, Any]]:
    """Use the largest connected near-ab=0 region as the basal starting point."""
    longitudinal = np.asarray(
        selected_surface.point_data["__cardiaccore_ring_longitudinal"]
    )
    threshold = float(np.min(longitudinal) + 0.05 * np.ptp(longitudinal))
    in_reference = longitudinal <= threshold
    adjacency = {
        int(point_id): set() for point_id in np.flatnonzero(in_reference)
    }
    faces = np.asarray(selected_surface.faces, dtype=int)
    offset = 0
    while offset < len(faces):
        count = int(faces[offset])
        point_ids = [
            int(point_id)
            for point_id in faces[offset + 1:offset + count + 1]
            if in_reference[point_id]
        ]
        for point_id in point_ids:
            adjacency[point_id].update(
                other_id for other_id in point_ids if other_id != point_id
            )
        offset += count + 1

    remaining = set(adjacency)
    components: list[set[int]] = []
    while remaining:
        stack = [remaining.pop()]
        component: set[int] = set()
        while stack:
            point_id = stack.pop()
            component.add(point_id)
            for neighbour in adjacency[point_id]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
        components.append(component)
    selected_component = max(components, key=len)
    reference_ids = np.asarray(sorted(selected_component), dtype=int)
    return np.asarray(selected_surface.points)[reference_ids], {
        "ab_zero_threshold": threshold,
        "ab_zero_component_count": len(components),
        "selected_ab_zero_component_point_count": int(len(reference_ids)),
    }


def _contour_loop_report(
    contour: Any,
    level: float,
    ab_zero_reference: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray | None]:
    """Select the closed component physically nearest to the ab=0 reference."""
    components = _contour_components(contour)
    closed_components = [
        (index, point_ids)
        for index, (point_ids, closed) in enumerate(components)
        if closed
    ]
    selected_ids: np.ndarray | None = None
    selected_index: int | None = None
    selected_distance: float | None = None
    if closed_components:
        selected_index, selected_ids = min(
            closed_components,
            key=lambda item: _minimum_point_distance(
                np.asarray(contour.points)[item[1]], ab_zero_reference,
            ),
        )
        selected_distance = _minimum_point_distance(
            np.asarray(contour.points)[selected_ids], ab_zero_reference,
        )
    closed_component_count = len(closed_components)
    report = {
        "longitudinal_level": float(level), "point_count": int(contour.n_points),
        "component_count": len(components),
        "closed_component_count": closed_component_count,
        "single_closed_ring": len(components) == 1 and closed_component_count == 1,
        "has_selected_closed_component": selected_ids is not None,
        "selected_closed_component_index": selected_index,
        "selected_closed_component_point_count": (
            int(len(selected_ids)) if selected_ids is not None else 0
        ),
        "selected_closed_component_distance_to_ab0": selected_distance,
        "closed_component_fallback_used": bool(len(components) > 1 and selected_ids is not None),
    }
    return report, selected_ids


def _basal_ring_spacing_report(
    selected_surface: Any,
    selected_component_points: tuple[np.ndarray | None, ...],
    rings: tuple[dict[str, Any], ...],
    tolerance: float,
) -> dict[str, Any]:
    """Measure the 0.1-to-0.4 ring separation against chamber extent.

    The two iso-values alone cannot establish that their contours sample the
    intended basal interval: a malformed coordinate can place a locally closed
    0.1 contour near the valve end.  The axis is therefore defined by the two
    contour centres and normalized by the selected endocardial surface extent
    along that direction.
    """
    report: dict[str, Any] = {
        "from_longitudinal_level": float(_BASAL_RING_LEVELS[0]),
        "to_longitudinal_level": float(_BASAL_RING_LEVELS[1]),
        "expected_normalized_distance": _BASAL_RING_SPACING_FRACTION,
        "tolerance": float(tolerance),
        "normalized_centroid_distance": None,
        "within_expected_range": False,
    }
    if not all(ring["has_selected_closed_component"] for ring in rings):
        report["reason"] = "both_basal_levels_must_have_a_closed_component"
        return report

    centres = [
        np.mean(points, axis=0) for points in selected_component_points
    ]
    direction = centres[1] - centres[0]
    centroid_distance = float(np.linalg.norm(direction))
    if np.isclose(centroid_distance, 0.0):
        report["reason"] = "basal_ring_centres_coincide"
        return report
    unit_direction = direction / centroid_distance
    projections = np.asarray(selected_surface.points) @ unit_direction
    chamber_span = float(np.max(projections) - np.min(projections))
    if np.isclose(chamber_span, 0.0):
        report["reason"] = "endocardial_surface_has_zero_span_along_ring_axis"
        return report

    normalized_distance = centroid_distance / chamber_span
    report.update({
        "centroid_distance": centroid_distance,
        "endocardial_axis_span": chamber_span,
        "normalized_centroid_distance": normalized_distance,
        "within_expected_range": bool(
            abs(normalized_distance - _BASAL_RING_SPACING_FRACTION) <= tolerance
        ),
    })
    return report


def _coordinate_field_candidates(
    surface: Any,
    mesh_path: Path,
    binary_tolerance: float,
    seam_point_fraction_tolerance: float,
) -> tuple[tuple[str, tuple[float, float]], tuple[str, ...]]:
    """Return numerical chamber and continuous-coordinate candidates.

    This intentionally classifies field behaviour rather than names.  The
    two-valued field is only a chamber *candidate*; topology later determines
    whether a complete field triple supports the requested ring criterion.
    """
    scalar_names = []
    values_by_name: dict[str, np.ndarray] = {}
    for name in sorted(set(surface.point_data) | set(surface.cell_data)):
        try:
            values = _mesh_point_scalar(surface, name, mesh_path)
        except (KeyError, ValueError):
            continue
        scalar_names.append(name)
        values_by_name[name] = values

    binary = []
    continuous = []
    for name in scalar_names:
        values = values_by_name[name]
        unique = np.unique(values)
        chamber_values = None
        if len(unique) >= 2 and np.all(np.abs((unique[0], unique[-1])) <= 1.0 + binary_tolerance):
            accepted, _, _ = _binary_chamber_with_seam(
                values,
                float(unique[0]),
                float(unique[-1]),
                binary_tolerance,
                seam_point_fraction_tolerance,
            )
            if accepted:
                chamber_values = (float(unique[0]), float(unique[-1]))
                binary.append((name, chamber_values))
        if chamber_values is None and (
            len(unique) > 2
            and float(np.min(values)) >= -binary_tolerance
            and float(np.max(values)) <= 1.0 + binary_tolerance
            and np.ptp(values) > binary_tolerance
        ):
            continuous.append(name)
    return tuple(binary), tuple(continuous)


def discover_coordinate_ring_candidates_from_vtk(
    mesh_path: Path,
    endocardial_band: float = 0.05,
    ring_levels: np.ndarray = _BASAL_RING_LEVELS,
    binary_tolerance: float = 1e-9,
    basal_ring_spacing_tolerance: float = 0.1,
    seam_point_fraction_tolerance: float = _MAX_SEAM_POINT_FRACTION,
) -> dict[str, Any]:
    """Infer coordinate-field candidates from values and ring topology.

    Field names are not a convention. A candidate requires a two-valued
    chamber field in the expected normalized range, two varying normalized
    scalar fields, an endocardial boundary at either scalar endpoint, and a
    one closed component for both chamber values at basal levels 0.1 and 0.4.
    If a level has multiple components, the closed component nearest to the
    largest connected ab=0 endocardial reference is selected. Their normalized
    separation must be approximately 0.3. A unique candidate is resolved;
    multiple candidates remain ambiguous and no LV/RV naming is invented from
    their numeric order.
    """
    ring_levels = _fixed_basal_ring_levels(ring_levels)
    seam_point_fraction_tolerance = float(seam_point_fraction_tolerance)
    if not 0 <= seam_point_fraction_tolerance <= 1:
        raise ValueError(
            "seam_point_fraction_tolerance must be a fraction in [0, 1]"
        )
    pv = _pyvista()
    mesh = pv.read(str(mesh_path))
    if mesh.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no cells")
    surface = mesh.extract_surface(algorithm="dataset_surface").triangulate().clean()
    if surface.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no boundary surface cells")
    binary, continuous = _coordinate_field_candidates(
        surface,
        mesh_path,
        float(binary_tolerance),
        seam_point_fraction_tolerance,
    )
    if not binary:
        return {
            "status": "no_binary_chamber_field",
            "binary_chamber_candidates": tuple(),
            "continuous_scalar_candidates": continuous,
        }
    if len(continuous) < 2:
        return {
            "status": "insufficient_continuous_fields",
            "binary_chamber_candidates": binary,
            "continuous_scalar_candidates": continuous,
        }

    resolved = []
    for chamber_field, chamber_values in binary:
        for longitudinal_field in continuous:
            for transmural_field in continuous:
                if longitudinal_field == transmural_field:
                    continue
                transmural_values = _mesh_point_scalar(
                    surface, transmural_field, mesh_path,
                )
                for endocardial_value in (
                    float(np.min(transmural_values)),
                    float(np.max(transmural_values)),
                ):
                    report = coordinate_endocardial_ring_closure_from_vtk(
                        mesh_path,
                        chamber_field,
                        longitudinal_field,
                        transmural_field,
                        chamber_values[0],
                        chamber_values[1],
                        endocardial_value,
                        endocardial_band,
                        ring_levels,
                        binary_tolerance,
                        basal_ring_spacing_tolerance,
                        seam_point_fraction_tolerance,
                    )
                    if (
                        report["coordinate_contract"]["intraventricular_binary"]
                        and report["lv"].get("basal_ring_preflight_passed", False)
                        and report["rv"].get("basal_ring_preflight_passed", False)
                    ):
                        resolved.append({
                            "intraventricular_field": chamber_field,
                            "chamber_values": chamber_values,
                            "longitudinal_field": longitudinal_field,
                            "transmural_field": transmural_field,
                            "endocardial_value": endocardial_value,
                            "first_chamber": report["lv"],
                            "second_chamber": report["rv"],
                        })
    if len(resolved) == 1:
        status = "resolved"
    elif resolved:
        status = "ambiguous"
    else:
        status = "no_closed_ring_candidate"
    return {
        "status": status,
        "binary_chamber_candidates": binary,
        "continuous_scalar_candidates": continuous,
        "ring_candidates": tuple(resolved),
    }


def coordinate_endocardial_ring_closure_from_vtk(
    mesh_path: Path,
    intraventricular_field: str | None = None,
    longitudinal_field: str | None = None,
    transmural_field: str | None = None,
    lv_value: float | None = None,
    rv_value: float | None = None,
    endocardial_value: float | None = None,
    endocardial_band: float = 0.05,
    ring_levels: np.ndarray = _BASAL_RING_LEVELS,
    binary_tolerance: float = 1e-9,
    basal_ring_spacing_tolerance: float = 0.1,
    seam_point_fraction_tolerance: float = _MAX_SEAM_POINT_FRACTION,
) -> dict[str, Any]:
    """Check LV/RV endocardial longitudinal contours from coordinate fields.

    With the three field names and values omitted, the function reports the
    topology-supported field candidates discovered from the mesh. Explicit
    fields retain the path that labels the two values LV/RV. Every path is
    read-only.
    """
    automatic = (
        intraventricular_field is None and longitudinal_field is None
        and transmural_field is None and lv_value is None and rv_value is None
        and endocardial_value is None
    )
    if automatic:
        return {
            "coordinate_discovery": discover_coordinate_ring_candidates_from_vtk(
                mesh_path,
                endocardial_band,
                ring_levels,
                binary_tolerance,
                basal_ring_spacing_tolerance,
                seam_point_fraction_tolerance,
            ),
            "coordinate_contract": None,
            "lv": None,
            "rv": None,
        }
    elif any(value is None for value in (
        intraventricular_field, longitudinal_field, transmural_field,
        lv_value, rv_value, endocardial_value,
    )):
        raise ValueError(
            "provide every coordinate field/value or omit all of them for detection"
        )

    pv = _pyvista()
    if not all((intraventricular_field, longitudinal_field, transmural_field)):
        raise ValueError("coordinate field names must be non-empty")
    try:
        lv_value, rv_value, endocardial_value = (
            float(value) for value in (lv_value, rv_value, endocardial_value)
        )
        endocardial_band = float(endocardial_band)
        basal_ring_spacing_tolerance = float(basal_ring_spacing_tolerance)
        binary_tolerance = float(binary_tolerance)
        seam_point_fraction_tolerance = float(seam_point_fraction_tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("coordinate values and tolerances must be scalar numbers") from exc
    if not all(np.isfinite(value) for value in (lv_value, rv_value, endocardial_value)):
        raise ValueError("coordinate values must be finite")
    if lv_value == rv_value:
        raise ValueError("lv_value and rv_value must differ")
    if not np.isfinite(endocardial_band) or endocardial_band <= 0:
        raise ValueError("endocardial_band must be a positive finite scalar")
    if (
        not np.isfinite(basal_ring_spacing_tolerance)
        or basal_ring_spacing_tolerance < 0
    ):
        raise ValueError(
            "basal_ring_spacing_tolerance must be a finite non-negative scalar"
        )
    if not np.isfinite(binary_tolerance) or binary_tolerance < 0:
        raise ValueError("binary_tolerance must be a finite non-negative scalar")
    if not 0 <= seam_point_fraction_tolerance <= 1:
        raise ValueError(
            "seam_point_fraction_tolerance must be a fraction in [0, 1]"
        )
    levels = _fixed_basal_ring_levels(ring_levels)

    mesh = pv.read(str(mesh_path))
    if mesh.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no cells")
    surface = mesh.extract_surface(algorithm="dataset_surface").triangulate().clean()
    if surface.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no boundary surface cells")
    point_iv = _mesh_point_scalar(surface, intraventricular_field, mesh_path)
    point_longitudinal = _mesh_point_scalar(surface, longitudinal_field, mesh_path)
    cell_iv = _mesh_cell_scalar(surface, intraventricular_field, mesh_path)
    cell_transmural = _mesh_cell_scalar(surface, transmural_field, mesh_path)

    binary, seam_count, seam_fraction = _binary_chamber_with_seam(
        point_iv,
        lv_value,
        rv_value,
        binary_tolerance,
        seam_point_fraction_tolerance,
    )
    lower_chamber_value, upper_chamber_value = sorted((lv_value, rv_value))
    outside_chamber_interval = (point_iv < lower_chamber_value - binary_tolerance) | (
        point_iv > upper_chamber_value + binary_tolerance
    )
    coordinate_contract = {
        "intraventricular_binary": binary,
        "intraventricular_nonbinary_point_count": int(
            np.count_nonzero(outside_chamber_interval)
        ),
        "intraventricular_seam_point_count": seam_count,
        "intraventricular_seam_point_fraction": seam_fraction,
        "longitudinal_varies": bool(np.ptp(point_longitudinal) > 0),
        "longitudinal_min": float(np.min(point_longitudinal)),
        "longitudinal_max": float(np.max(point_longitudinal)),
    }
    if not coordinate_contract["intraventricular_binary"]:
        return {
            "coordinate_contract": coordinate_contract, "lv": None, "rv": None,
        }

    surface.point_data["__cardiaccore_ring_longitudinal"] = point_longitudinal
    endocardial = np.abs(cell_transmural - endocardial_value) <= endocardial_band
    reports: dict[str, Any] = {"coordinate_contract": coordinate_contract}
    for chamber, chamber_value in (("lv", lv_value), ("rv", rv_value)):
        nearest_chamber = np.abs(cell_iv - chamber_value) <= np.abs(
            cell_iv - (rv_value if chamber == "lv" else lv_value)
        )
        selected = surface.extract_cells(np.flatnonzero(endocardial & nearest_chamber))
        selected = selected.extract_surface(algorithm="dataset_surface").triangulate().clean()
        if selected.n_cells == 0:
            reports[chamber] = {"surface_cell_count": 0, "rings": tuple()}
            continue
        ab_zero_reference, ab_zero_report = _largest_ab_zero_reference(selected)
        contours = tuple(
            (
                float(level),
                selected.contour(
                    isosurfaces=[float(level)],
                    scalars="__cardiaccore_ring_longitudinal",
                ).clean(),
            )
            for level in levels
        )
        ring_details = tuple(
            _contour_loop_report(contour, level, ab_zero_reference)
            for level, contour in contours
        )
        rings = tuple(report for report, _ in ring_details)
        selected_component_points = tuple(
            (
                np.asarray(contour.points)[selected_ids]
                if selected_ids is not None else None
            )
            for (_, contour), (_, selected_ids) in zip(contours, ring_details)
        )
        basal_ring_spacing = _basal_ring_spacing_report(
            selected, selected_component_points, rings, basal_ring_spacing_tolerance,
        )
        all_rings_closed = bool(rings) and all(
            ring["has_selected_closed_component"] for ring in rings
        )
        reports[chamber] = {
            "surface_cell_count": int(selected.n_cells),
            "ab_zero_reference": ab_zero_report,
            "rings": rings,
            "all_requested_rings_closed": all_rings_closed,
            "basal_ring_spacing": basal_ring_spacing,
            "basal_ring_preflight_passed": bool(
                all_rings_closed
                and basal_ring_spacing["within_expected_range"]
            ),
        }
    return reports
