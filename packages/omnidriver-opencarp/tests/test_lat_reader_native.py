"""The LAT reader against the real binary: values at supplied points, in ms,
interpolated over the mesh the solve used. Every mesh read here was written
by mesher; no geometry is invented."""
from __future__ import annotations

import dataclasses

import pytest

from omnidriver.core.quantities import ReadRequest, read_quantities
from omnidriver.opencarp.lat_reader import LatPerNodeReader
from opencarp_native import niederer_run

pytestmark = pytest.mark.native_opencarp

CORNERS = {f"x{x}y{y}z{z}": (float(x), float(y), float(z)) for x in (0, 20000) for y in (0, 7000) for z in (0, 3000)}
CENTRE = {"centre": (10000.0, 3500.0, 1500.0)}


def _read_mesh(case_root, mesh_name: str):
    """Independent parse of mesher's own files: a node list and a list of
    ``(n0, n1, n2, n3)`` tetrahedra, both by point index."""
    pts_count, *pts_rows = (case_root / f"{mesh_name}.pts").read_text().split("\n")
    points = [tuple(float(v) for v in row.split()) for row in pts_rows if row.strip()]
    assert len(points) == int(pts_count)
    elem_count, *elem_rows = (case_root / f"{mesh_name}.elem").read_text().split("\n")
    tets = [tuple(int(v) for v in row.split()[1:5]) for row in elem_rows if row.strip()]
    assert len(tets) == int(elem_count)
    return points, tets


def test_the_slab_corners_and_centre_at_dx_500_match_g4(tmp_path):
    run = niederer_run(tmp_path, dx=500.0, tend=150.0)
    points = {**CORNERS, **CENTRE}
    quantities = {q.name: q for q in read_quantities(
        LatPerNodeReader(), run.case_root, run.lat_artifact, ReadRequest(names=tuple(points), points=points))}
    assert all(q.status == "evaluated" and q.unit == "ms" and q.sampling_rule == "linear" for q in quantities.values())
    # every requested point is a mesh node here (a 41 x 15 x 7 slab), so the
    # interpolated value is exactly that node's, and the offset is 0 either way
    assert all(q.sampled_at == points[name] and q.sampled_at_unit == "um" for name, q in quantities.items())
    assert quantities["x0y0z0"].value == pytest.approx(1.355, abs=5e-4)             # P1, 1.355 ms
    assert quantities["x20000y7000z3000"].value == pytest.approx(126.45, abs=5e-3)  # P8, 126.45 ms
    assert quantities["x0y0z0"].value < quantities["centre"].value < quantities["x20000y7000z3000"].value


def test_a_node_never_reached_is_not_reached_never_minus_one(tmp_path):
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
    far = {"far": (20000.0, 7000.0, 3000.0)}
    (quantity,) = read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                  ReadRequest(names=("far",), points=far))
    assert (quantity.status, quantity.value) == ("not_reached", None)


def test_a_point_inside_a_tet_returns_the_barycentric_mix(tmp_path):
    """The centroid of a real tet weighs its four corners equally (1/4 each),
    against the solve's own LAT values -- no synthetic field needed."""
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
    points, tets = _read_mesh(run.case_root, "slab")
    lat_values = [float(v) for v in (run.case_root / run.lat_artifact.path_pattern).read_text().split()]
    tet = next(t for t in tets if all(lat_values[n] != -1.0 for n in t))  # inside the activated region
    corners = [points[n] for n in tet]
    centroid = tuple(sum(c[axis] for c in corners) / 4.0 for axis in range(3))
    expected = sum(lat_values[n] for n in tet) / 4.0
    (quantity,) = read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                  ReadRequest(names=("mid",), points={"mid": centroid}))
    assert quantity.status == "evaluated"
    assert quantity.value == pytest.approx(expected, abs=1e-9)
    assert quantity.sampled_at == centroid and quantity.sampling_rule == "linear"


def test_p9_at_dx_0_2mm_is_the_mean_of_its_four_equidistant_nodes(tmp_path):
    """At dx 0.2 mm, P9 (10000, 3500, 1500) um sits at the centre of a square
    face shared by tets (y in {3400, 3600}, z in {1400, 1600} um), equidistant
    from its four corners -- a tie between nodes that a nearest-node reader
    cannot resolve, so the reader must interpolate instead. The mesh is real
    (mesher's dx-200 slab); the LAT field is a synthetic affine function of
    position (not the solve's own physics), so the analytically exact value
    at P9 is known and equals the mean of the four corners regardless of
    which of the tets touching that shared face answers the query."""
    run = niederer_run(tmp_path, dx=200.0, tend=10.0)
    points, _ = _read_mesh(run.case_root, "slab")

    def field(point: tuple[float, float, float]) -> float:
        return point[0] + 2.0 * point[1] + 3.0 * point[2]

    lat_path = run.case_root / run.lat_artifact.path_pattern
    lat_path.write_text("\n".join(repr(field(p)) for p in points) + "\n")

    corner_coords = [(10000.0, y, z) for y in (3400.0, 3600.0) for z in (1400.0, 1600.0)]
    corner_indices = [points.index(c) for c in corner_coords]
    expected_mean = sum(field(points[i]) for i in corner_indices) / 4.0
    p9 = CENTRE["centre"]
    assert p9 not in points  # the tie: no node sits at P9 itself
    assert expected_mean == pytest.approx(field(p9))  # true of any affine field at a parallelogram's centre

    (quantity,) = read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                  ReadRequest(names=("P9",), points={"P9": p9}))
    assert quantity.status == "evaluated"
    assert quantity.value == pytest.approx(expected_mean, abs=1e-6)
    assert quantity.sampled_at == p9 and quantity.sampled_at_unit == "um"


def test_a_point_outside_the_mesh_is_refused_by_name(tmp_path):
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
    outside = {"outside": (-5000.0, 3500.0, 1500.0)}
    with pytest.raises(ValueError, match="'outside'.*no element"):
        LatPerNodeReader().read(run.case_root, run.lat_artifact, ReadRequest(names=("outside",), points=outside))


def test_the_per_event_layout_is_refused_by_name(tmp_path):
    """With lats[0].all = 1 the declared per-node file is absent, and the
    file openCARP does write has two columns, which the reader refuses."""
    # nversion.par:lats[0].all is catalogued as an Int (0/1), not a Flag
    # (opencarp_parameters.json: "name": "lats[Int].all", "type": "Int"), so
    # the study value must be an int -- a bool is refused by the generic
    # value-shape check ("must be an integer", contracts/dictionary.py).
    # allow_missing_declared_artifact=True is this test's own concession, not
    # the shared helper's default: with all = 1 the declared LAT file is
    # expected to be absent (that is the point of this test), and
    # reconciliation marks the case failed even though openCARP exits 0. Any
    # other caller of niederer_run/niederer_sweep still fails loudly on a
    # missing declared artifact.
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0, extra={"nversion.par:lats[0].all": 1},
                       allow_missing_declared_artifact=True)
    assert not (run.case_root / run.lat_artifact.path_pattern).exists()
    per_event = dataclasses.replace(run.lat_artifact, path_pattern="out/vm_act-thresh.dat")
    with pytest.raises(ValueError, match=r"lats\[\]\.all = 1"):
        LatPerNodeReader().read(run.case_root, per_event,
                                ReadRequest(names=("origin",), points={"origin": (0.0, 0.0, 0.0)}))
