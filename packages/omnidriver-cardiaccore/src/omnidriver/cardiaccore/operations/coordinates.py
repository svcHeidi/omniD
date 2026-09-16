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


def _contour_loop_report(contour: Any, level: float) -> dict[str, Any]:
    """Summarize whether every connected contour component is a closed loop."""
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
        return {
            "longitudinal_level": float(level), "point_count": int(contour.n_points),
            "component_count": 0, "closed_component_count": 0,
            "single_closed_ring": False,
        }

    adjacency: dict[int, set[int]] = {}
    for left, right in edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    remaining = set(adjacency)
    closed_components = 0
    components = 0
    while remaining:
        components += 1
        stack = [remaining.pop()]
        component: set[int] = set()
        while stack:
            point_id = stack.pop()
            component.add(point_id)
            for neighbour in adjacency[point_id]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    stack.append(neighbour)
        if all(len(adjacency[point_id]) == 2 for point_id in component):
            closed_components += 1
    return {
        "longitudinal_level": float(level), "point_count": int(contour.n_points),
        "component_count": components, "closed_component_count": closed_components,
        "single_closed_ring": components == 1 and closed_components == 1,
    }


def _coordinate_field_candidates(
    surface: Any,
    mesh_path: Path,
    binary_tolerance: float,
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
        if len(unique) == 2 and np.all(np.abs(unique) <= 1.0 + binary_tolerance):
            binary.append((name, (float(unique[0]), float(unique[1]))))
        if (
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
    ring_levels: np.ndarray = (0.2, 0.4, 0.6, 0.8),
    binary_tolerance: float = 1e-9,
) -> dict[str, Any]:
    """Infer coordinate-field candidates from values and ring topology.

    Field names are not a convention. A candidate requires a two-valued
    chamber field in the expected normalized range, two varying normalized
    scalar fields, an endocardial boundary at either scalar endpoint, and a
    monotonic sequence of one closed contour for both chamber values at every
    requested longitudinal level. A unique candidate is resolved; multiple
    candidates remain ambiguous and no LV/RV naming is invented from their
    numeric order.
    """
    pv = _pyvista()
    mesh = pv.read(str(mesh_path))
    if mesh.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no cells")
    surface = mesh.extract_surface(algorithm="dataset_surface").triangulate().clean()
    if surface.n_cells == 0:
        raise ValueError(f"{mesh_path}: mesh has no boundary surface cells")
    binary, continuous = _coordinate_field_candidates(
        surface, mesh_path, float(binary_tolerance),
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
                    )
                    if (
                        report["coordinate_contract"]["intraventricular_binary"]
                        and report["lv"].get("all_requested_rings_closed", False)
                        and report["rv"].get("all_requested_rings_closed", False)
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
    ring_levels: np.ndarray = (0.2, 0.4, 0.6, 0.8),
    binary_tolerance: float = 1e-9,
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
                mesh_path, endocardial_band, ring_levels, binary_tolerance,
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
        binary_tolerance = float(binary_tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError("coordinate values and tolerances must be scalar numbers") from exc
    if not all(np.isfinite(value) for value in (lv_value, rv_value, endocardial_value)):
        raise ValueError("coordinate values must be finite")
    if lv_value == rv_value:
        raise ValueError("lv_value and rv_value must differ")
    if not np.isfinite(endocardial_band) or endocardial_band <= 0:
        raise ValueError("endocardial_band must be a positive finite scalar")
    if not np.isfinite(binary_tolerance) or binary_tolerance < 0:
        raise ValueError("binary_tolerance must be a finite non-negative scalar")
    levels = np.asarray(ring_levels, dtype=float)
    if levels.ndim != 1 or not len(levels) or not np.all(np.isfinite(levels)):
        raise ValueError("ring_levels must be a non-empty finite one-dimensional array")
    if len(np.unique(levels)) != len(levels):
        raise ValueError("ring_levels must not contain duplicates")

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

    binary = np.isclose(point_iv, lv_value, atol=binary_tolerance) | np.isclose(
        point_iv, rv_value, atol=binary_tolerance
    )
    coordinate_contract = {
        "intraventricular_binary": bool(np.all(binary)),
        "intraventricular_nonbinary_point_count": int(np.count_nonzero(~binary)),
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
        rings = tuple(
            _contour_loop_report(
                selected.contour(
                    isosurfaces=[float(level)],
                    scalars="__cardiaccore_ring_longitudinal",
                ).clean(),
                float(level),
            )
            for level in levels
        )
        reports[chamber] = {
            "surface_cell_count": int(selected.n_cells),
            "rings": rings,
            "all_requested_rings_closed": bool(rings) and all(
                ring["single_closed_ring"] for ring in rings
            ),
        }
    return reports
