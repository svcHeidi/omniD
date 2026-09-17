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


def test_native_file_bridge_preserves_explicit_units_and_dimensionless_offsets(tmp_path):
    pv = pytest.importorskip("pyvista")
    from omnidriver.cardiaccore.operations.electrodes import (
        apply_offset_bundle_to_native_file,
        derive_reference_offset_bundle,
        read_reference_offset_bundle,
        write_electrode_positions,
        write_reference_offset_bundle,
    )

    points, chamber, longitudinal = _cloud()
    mesh = pv.PolyData(points)
    # A UVC case: its coordinate fields carry UVC names. UVC is one of the two
    # coordinate systems a case may declare, not an older spelling of the
    # other, so the reader is told the names rather than assuming any.
    mesh.point_data["uvc_intraventricular"] = chamber
    mesh.point_data["uvc_longitudinal"] = longitudinal
    heart = tmp_path / "heart.vtp"
    mesh.save(heart)
    reference = {"V1": [1.0, 2.0, 3.0], "V2": [2.0, 3.0, 4.0]}

    uvc_fields = {"intraventricular_field": "uvc_intraventricular",
                  "longitudinal_field": "uvc_longitudinal"}
    bundle = derive_reference_offset_bundle(
        heart, reference, coordinate_unit="mm", **uvc_fields
    )
    bundle_path = tmp_path / "offsets.json"
    write_reference_offset_bundle(bundle_path, bundle)
    loaded = read_reference_offset_bundle(bundle_path)
    positions = apply_offset_bundle_to_native_file(
        heart, loaded, target_coordinate_unit="mm", **uvc_fields
    )
    output_path = tmp_path / "electrodes.json"
    write_electrode_positions(output_path, positions)

    assert positions["target_coordinate_unit"] == "mm"
    for name, reference_position in reference.items():
        assert positions["electrodes"][name] == pytest.approx(reference_position)
    assert "normalized_offsets" in bundle
    assert output_path.exists()


def test_native_file_bridge_requires_explicit_unit_labels(tmp_path):
    from omnidriver.cardiaccore.operations.electrodes import (
        derive_reference_offset_bundle,
    )

    with pytest.raises(ValueError, match="coordinate_unit"):
        derive_reference_offset_bundle(
            tmp_path / "reference.vtp", {"V1": [0, 0, 0]}, coordinate_unit=""
        )
