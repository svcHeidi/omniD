"""Reference-frame ECG electrode transfer for supported comparative studies.

This is a geometry-normalized approximation derived from the Strocchi-02
reference anatomy. It is not a patient-specific electrode-placement model and
must be selected explicitly by a workflow; it never supplies a default
electrode configuration.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


LV_APEX_LONGITUDINAL_MAX = 0.2
LV_BASE_LONGITUDINAL_MIN = 0.8

REFERENCE_LOCAL_OFFSETS: dict[str, list[float]] = {
    "V1": [0.17202851655061616, 0.28296924534866114, 1.1106200110781466],
    "V2": [-0.09392335329324816, -0.16919747507168265, 0.872009294844085],
    "V3": [-0.3997038760866017, -0.23479326210248155, 0.7063028601877519],
    "V4": [-0.683693051758297, -0.4584839288383385, 0.3203462826799792],
    "V5": [-0.7457586101211467, -0.6790317373202257, -0.08798427038899685],
    "V6": [-0.6925276529190797, -0.8104441341181372, -0.40296292163474073],
}

ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LVFrame:
    """LV-centred, apex-to-base anatomical frame."""

    lv_centre: np.ndarray
    l_hat: np.ndarray
    s_hat: np.ndarray
    a_hat: np.ndarray
    size: float

    @property
    def rotation(self) -> np.ndarray:
        return np.column_stack([self.l_hat, self.s_hat, self.a_hat])


def compute_lv_frame(
    points: np.ndarray,
    uvc_intraventricular: np.ndarray,
    uvc_longitudinal: np.ndarray,
) -> LVFrame:
    """Build the point-sampled LV frame used by the reference transfer."""
    points = np.asarray(points, dtype=float)
    chamber = np.asarray(uvc_intraventricular, dtype=float)
    longitudinal = np.asarray(uvc_longitudinal, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or chamber.ndim != 1 or longitudinal.ndim != 1:
        raise ValueError("points must be Nx3 and UVC fields must be one-dimensional arrays")
    if not (len(points) == len(chamber) == len(longitudinal)):
        raise ValueError("points and UVC arrays must have equal lengths")
    if not all(np.all(np.isfinite(values)) for values in (points, chamber, longitudinal)):
        raise ValueError("points and UVC fields must contain only finite values")

    lv_mask, rv_mask = chamber < 0.0, chamber > 0.0
    if not np.any(lv_mask):
        raise ValueError("no LV points (uvc_intraventricular < 0)")
    if not np.any(rv_mask):
        raise ValueError("no RV points (uvc_intraventricular > 0)")
    apex_mask = lv_mask & (longitudinal < LV_APEX_LONGITUDINAL_MAX)
    base_mask = lv_mask & (longitudinal > LV_BASE_LONGITUDINAL_MIN)
    if not np.any(apex_mask) or not np.any(base_mask):
        raise ValueError("LV point data must include apex (<0.2) and base (>0.8) bands")

    lv_centre, rv_centre = points[lv_mask].mean(axis=0), points[rv_mask].mean(axis=0)
    axis = points[base_mask].mean(axis=0) - points[apex_mask].mean(axis=0)
    size = float(np.linalg.norm(axis))
    if size < 1e-9:
        raise ValueError("apex and base centroids coincide; cannot form Lhat")
    l_hat = axis / size
    septal = rv_centre - lv_centre
    septal -= np.dot(septal, l_hat) * l_hat
    norm = np.linalg.norm(septal)
    if norm < 1e-9:
        raise ValueError("RV centre lies on the LV long axis; cannot form Shat")
    s_hat = septal / norm
    return LVFrame(lv_centre, l_hat, s_hat, np.cross(l_hat, s_hat), size)


def encode_to_local(point: np.ndarray, frame: LVFrame) -> np.ndarray:
    """Apply rotation and translation, then normalize by LV long-axis size."""
    return frame.rotation.T @ (np.asarray(point, dtype=float) - frame.lv_centre) / frame.size


def decode_from_local(
    local_normalized: np.ndarray, frame: LVFrame, axial_shift: float = 0.0,
) -> np.ndarray:
    """Invert the reference transform; axial shift is a separate opt-in step."""
    decoded = frame.lv_centre + frame.rotation @ (np.asarray(local_normalized) * frame.size)
    return decoded + axial_shift * frame.size * frame.l_hat


def apply_reference_offsets(frame: LVFrame, *, axial_shift: float = 0.0) -> dict[str, list[float]]:
    """Return Strocchi-02 reference offsets reconstructed for ``frame``."""
    return {
        name: decode_from_local(np.asarray(offset), frame, axial_shift).tolist()
        for name, offset in REFERENCE_LOCAL_OFFSETS.items()
    }


def read_native_electrode_fields(
    heart_vtk: Path,
    *,
    intraventricular_field: str = "uvc_intraventricular",
    longitudinal_field: str = "uvc_longitudinal",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read the point-aligned UVC arrays needed to construct an LV frame.

    Native ``foamToVTK`` exports can carry UVC arrays as cell data.  They are
    converted to point data before reading, exactly as required by the
    point-sampled :func:`compute_lv_frame` contract.  This function does not
    infer a physical coordinate unit: its caller records that unit alongside
    any resulting JSON artifact.
    """
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ValueError(
            "native electrode-file operations require omnidriver-cardiaccore[vtk]"
        ) from exc

    mesh = pv.read(str(heart_vtk))
    if mesh.n_points == 0:
        raise ValueError(f"{heart_vtk}: native VTK mesh has no points")
    if (
        intraventricular_field not in mesh.point_data
        or longitudinal_field not in mesh.point_data
    ):
        mesh = mesh.cell_data_to_point_data()
    missing = [
        name for name in (intraventricular_field, longitudinal_field)
        if name not in mesh.point_data
    ]
    if missing:
        raise ValueError(f"{heart_vtk}: native VTK point data is missing {missing}")
    intraventricular = np.asarray(mesh.point_data[intraventricular_field])
    longitudinal = np.asarray(mesh.point_data[longitudinal_field])
    if len(intraventricular) != mesh.n_points or len(longitudinal) != mesh.n_points:
        raise ValueError(f"{heart_vtk}: UVC fields are not point-aligned")
    return np.asarray(mesh.points), intraventricular, longitudinal


def _coordinate_unit(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("coordinate_unit must be a non-empty caller-declared string")
    return value.strip()


def _offset_mapping(value: Mapping[str, Any]) -> dict[str, list[float]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("normalized_offsets must be a non-empty mapping")
    offsets: dict[str, list[float]] = {}
    for name, offset in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError("each electrode name must be a non-empty string")
        vector = np.asarray(offset, dtype=float)
        if vector.shape != (3,) or not np.all(np.isfinite(vector)):
            raise ValueError(f"normalized offset {name!r} must be a finite length-3 coordinate")
        offsets[name] = vector.tolist()
    return offsets


def derive_reference_offset_bundle(
    reference_heart_vtk: Path,
    reference_electrodes: Mapping[str, Any],
    *,
    coordinate_unit: str,
) -> dict[str, Any]:
    """Encode supplied reference electrodes into a portable, dimensionless bundle.

    ``reference_electrodes`` and ``reference_heart_vtk`` must use the same
    caller-declared coordinate unit.  No metre-to-millimetre assumption is
    made.  The output offsets are dimensionless; the unit is provenance for
    the source reference, not a conversion instruction for a target case.
    """
    unit = _coordinate_unit(coordinate_unit)
    points, chamber, longitudinal = read_native_electrode_fields(reference_heart_vtk)
    frame = compute_lv_frame(points, chamber, longitudinal)
    electrodes = _offset_mapping(reference_electrodes)
    return {
        "schema_version": ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION,
        "source_heart_vtk": str(reference_heart_vtk),
        "source_coordinate_unit": unit,
        "normalized_offsets": {
            name: encode_to_local(np.asarray(position), frame).tolist()
            for name, position in electrodes.items()
        },
    }


def read_reference_offset_bundle(path: Path) -> dict[str, Any]:
    """Load and validate an explicitly unit-labelled offset bundle."""
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read electrode offset bundle {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: electrode offset bundle must be a JSON object")
    if payload.get("schema_version") != ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported electrode offset bundle schema "
            f"{payload.get('schema_version')!r}"
        )
    unit = _coordinate_unit(payload.get("source_coordinate_unit"))
    offsets = _offset_mapping(payload.get("normalized_offsets"))
    source = payload.get("source_heart_vtk")
    if not isinstance(source, str) or not source:
        raise ValueError(f"{path}: source_heart_vtk must be a non-empty string")
    return {
        "schema_version": ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION,
        "source_heart_vtk": source,
        "source_coordinate_unit": unit,
        "normalized_offsets": offsets,
    }


def write_reference_offset_bundle(path: Path, bundle: Mapping[str, Any]) -> None:
    """Validate and write one portable electrode-offset bundle as JSON."""
    validated = {
        "schema_version": ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION,
        "source_heart_vtk": bundle.get("source_heart_vtk"),
        "source_coordinate_unit": bundle.get("source_coordinate_unit"),
        "normalized_offsets": bundle.get("normalized_offsets"),
    }
    # Reuse the public reader's validation rather than let writers emit a
    # payload this package would later refuse.
    source = validated["source_heart_vtk"]
    if not isinstance(source, str) or not source:
        raise ValueError("source_heart_vtk must be a non-empty string")
    validated["source_coordinate_unit"] = _coordinate_unit(
        validated["source_coordinate_unit"]
    )
    validated["normalized_offsets"] = _offset_mapping(validated["normalized_offsets"])
    path.write_text(json.dumps(validated, indent=2, sort_keys=True) + "\n")


def apply_offset_bundle_to_native_file(
    heart_vtk: Path,
    bundle: Mapping[str, Any],
    *,
    target_coordinate_unit: str,
    axial_shift: float = 0.0,
) -> dict[str, Any]:
    """Decode a validated bundle on a target VTK anatomy without unit conversion."""
    unit = _coordinate_unit(target_coordinate_unit)
    source = bundle.get("source_heart_vtk")
    if not isinstance(source, str) or not source:
        raise ValueError("source_heart_vtk must be a non-empty string")
    if bundle.get("schema_version") != ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported electrode offset bundle schema")
    _coordinate_unit(bundle.get("source_coordinate_unit"))
    offsets = _offset_mapping(bundle.get("normalized_offsets"))
    points, chamber, longitudinal = read_native_electrode_fields(heart_vtk)
    frame = compute_lv_frame(points, chamber, longitudinal)
    return {
        "schema_version": ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION,
        "target_heart_vtk": str(heart_vtk),
        "target_coordinate_unit": unit,
        "source_offset_bundle": {
            "source_heart_vtk": source,
            "source_coordinate_unit": bundle["source_coordinate_unit"],
        },
        "electrodes": {
            name: decode_from_local(np.asarray(offset), frame, axial_shift=axial_shift).tolist()
            for name, offset in offsets.items()
        },
    }


def write_electrode_positions(path: Path, positions: Mapping[str, Any]) -> None:
    """Write the explicit, unit-labelled target positions returned by the file bridge."""
    required = {"schema_version", "target_heart_vtk", "target_coordinate_unit", "electrodes"}
    missing = required.difference(positions)
    if missing:
        raise ValueError("electrode position payload is missing " + ", ".join(sorted(missing)))
    if positions.get("schema_version") != ELECTRODE_OFFSET_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported electrode position payload schema")
    target = positions.get("target_heart_vtk")
    if not isinstance(target, str) or not target:
        raise ValueError("target_heart_vtk must be a non-empty string")
    payload = dict(positions)
    payload["target_coordinate_unit"] = _coordinate_unit(payload["target_coordinate_unit"])
    payload["electrodes"] = _offset_mapping(payload["electrodes"])
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
