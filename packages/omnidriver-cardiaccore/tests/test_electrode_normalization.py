import numpy as np
import pytest

from omnidriver.cardiaccore.operations.electrodes import (
    REFERENCE_LOCAL_OFFSETS,
    apply_reference_offsets,
    compute_lv_frame,
    decode_from_local,
    encode_to_local,
)


def _cloud():
    points, chamber, longitudinal = [], [], []
    for z in np.linspace(0, 10, 11):
        for angle in np.linspace(0, 2 * np.pi, 12, endpoint=False):
            points.extend(((np.cos(angle), np.sin(angle), z), (4 + np.cos(angle), np.sin(angle), z)))
            chamber.extend((-1.0, 1.0))
            longitudinal.extend((z / 10, z / 10))
    return np.asarray(points), np.asarray(chamber), np.asarray(longitudinal)


def test_frame_is_orthonormal_and_points_from_apex_to_base():
    frame = compute_lv_frame(*_cloud())
    assert frame.lv_centre == pytest.approx((0, 0, 5), abs=1e-6)
    assert frame.l_hat == pytest.approx((0, 0, 1), abs=1e-6)
    assert frame.rotation.T @ frame.rotation == pytest.approx(np.eye(3), abs=1e-9)


def test_reference_transform_round_trips_and_axial_shift_is_post_transform():
    frame = compute_lv_frame(*_cloud())
    point = np.array((1.3, -0.7, 6.5))
    assert decode_from_local(encode_to_local(point, frame), frame) == pytest.approx(point)
    shifted = decode_from_local(encode_to_local(point, frame), frame, axial_shift=0.5)
    assert shifted - point == pytest.approx(0.5 * frame.size * frame.l_hat)


def test_reference_offsets_are_explicit_not_a_default_case_configuration():
    frame = compute_lv_frame(*_cloud())
    reconstructed = apply_reference_offsets(frame)
    assert set(reconstructed) == set(REFERENCE_LOCAL_OFFSETS)
    assert all(len(value) == 3 for value in reconstructed.values())
