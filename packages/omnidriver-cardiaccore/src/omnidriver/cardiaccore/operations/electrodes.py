"""Reference-frame ECG electrode transfer for supported comparative studies.

This is a geometry-normalized approximation derived from the Strocchi-02
reference anatomy. It is not a patient-specific electrode-placement model and
must be selected explicitly by a workflow; it never supplies a default
electrode configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

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
