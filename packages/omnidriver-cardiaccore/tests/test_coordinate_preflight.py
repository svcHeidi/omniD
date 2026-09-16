import numpy as np


def _two_chamber_shell():
    import pyvista as pv

    points, faces, chamber, longitudinal, transmural = [], [], [], [], []
    for chamber_value, centre_x in ((0.0, 0.0), (1.0, 3.0)):
        for radius, wall_value in ((1.0, 1.0), (1.2, 0.0)):
            start = len(points)
            for z in (0.0, 0.5, 1.0):
                for index in range(8):
                    angle = 2 * np.pi * index / 8
                    points.append((centre_x + radius * np.cos(angle), radius * np.sin(angle), z))
                    chamber.append(chamber_value)
                    longitudinal.append(z)
                    transmural.append(wall_value if wall_value else 0.5 * z)
            for layer in range(2):
                for index in range(8):
                    following = (index + 1) % 8
                    lower = start + 8 * layer + index
                    upper = start + 8 * (layer + 1) + index
                    lower_next = start + 8 * layer + following
                    upper_next = start + 8 * (layer + 1) + following
                    faces.extend((3, lower, upper, lower_next, 3, lower_next, upper, upper_next))
    mesh = pv.PolyData(np.asarray(points), faces=np.asarray(faces))
    mesh.point_data["chamber_tag"] = np.asarray(chamber)
    mesh.point_data["height_coordinate"] = np.asarray(longitudinal)
    mesh.point_data["wall_coordinate"] = np.asarray(transmural)
    return mesh


def test_coordinate_preflight_discovers_role_from_topology_not_field_names(tmp_path):
    from omnidriver.cardiaccore.operations.coordinates import coordinate_endocardial_ring_closure_from_vtk

    path = tmp_path / "coordinate_mesh.vtp"
    _two_chamber_shell().save(path)

    report = coordinate_endocardial_ring_closure_from_vtk(
        path, endocardial_band=0.01, ring_levels=[0.25, 0.5, 0.75],
    )

    candidate = report["coordinate_discovery"]["ring_candidates"][0]
    assert report["coordinate_discovery"]["status"] == "resolved"
    assert candidate["intraventricular_field"] == "chamber_tag"
    assert candidate["longitudinal_field"] == "height_coordinate"
    assert candidate["transmural_field"] == "wall_coordinate"
    assert candidate["first_chamber"]["all_requested_rings_closed"] is True
    assert candidate["second_chamber"]["all_requested_rings_closed"] is True


def test_coordinate_preflight_reports_no_binary_chamber_field(tmp_path):
    from omnidriver.cardiaccore.operations.coordinates import coordinate_endocardial_ring_closure_from_vtk

    mesh = _two_chamber_shell()
    mesh.point_data["chamber_tag"][0] = 0.5
    path = tmp_path / "nonbinary_mesh.vtp"
    mesh.save(path)

    report = coordinate_endocardial_ring_closure_from_vtk(path)

    assert report["coordinate_discovery"]["status"] == "no_binary_chamber_field"
