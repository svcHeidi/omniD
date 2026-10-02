"""The LAT reader on what openCARP wrote for the Niederer slab at dx 1 mm, tend 10 ms:
the mesh ``mesher`` wrote (``slab.pts``, ``slab.elem``), the per-node LAT file and the
``parameters.par`` that names the mesh, committed verbatim, plus the per-event file
``lats[0].all = 1`` writes. No geometry is invented."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from omnidriver.core.quantities import ReadRequest, read_quantities
from omnidriver.core.runtime.models import DataArtifact
from omnidriver.opencarp.lat_reader import LAT_FORMAT, LatPerNodeReader

CASE = Path(__file__).resolve().parent / "fixtures" / "slab_dx1000"
LAT = DataArtifact(
    artifact_id="record.solve.0", path_pattern="out/init_acts_vm_act-thresh.dat", format=LAT_FORMAT,
    description="per-node local activation time", produced_by="solve",
)


def _mesh():
    points = [tuple(float(v) for v in row.split()) for row in (CASE / "slab.pts").read_text().splitlines()[1:] if row.strip()]
    tets = [tuple(int(v) for v in row.split()[1:5]) for row in (CASE / "slab.elem").read_text().splitlines()[1:] if row.strip()]
    values = [float(v) for v in (CASE / LAT.path_pattern).read_text().split()]
    return points, tets, values


def _read(points: dict[str, tuple[float, float, float]]):
    return {q.name: q for q in read_quantities(
        LatPerNodeReader(), CASE, LAT, ReadRequest(names=tuple(points), points=points))}


def test_a_mesh_node_reads_its_own_value_in_ms_at_the_point_asked():
    points, _tets, values = _mesh()
    origin = (0.0, 0.0, 0.0)
    quantity = _read({"origin": origin})["origin"]
    assert (quantity.status, quantity.unit, quantity.sampling_rule, quantity.sampled_at_unit) == ("evaluated", "ms", "linear", "um")
    assert quantity.sampled_at == origin
    assert quantity.value == pytest.approx(values[points.index(origin)], abs=1e-9)


def test_a_node_never_reached_is_not_reached_never_minus_one():
    far = (20000.0, 7000.0, 3000.0)
    _points, _tets, values = _mesh()
    assert -1.0 in values
    quantity = _read({"far": far})["far"]
    assert (quantity.status, quantity.value) == ("not_reached", None)


def test_a_point_inside_a_tet_returns_the_barycentric_mix_of_its_corners():
    points, tets, values = _mesh()
    tet = next(t for t in tets if all(values[n] != -1.0 for n in t))
    corners = [points[n] for n in tet]
    centroid = tuple(sum(c[axis] for c in corners) / 4.0 for axis in range(3))
    quantity = _read({"mid": centroid})["mid"]
    assert quantity.status == "evaluated"
    assert quantity.value == pytest.approx(sum(values[n] for n in tet) / 4.0, abs=1e-9)
    assert quantity.sampled_at == centroid and quantity.sampling_rule == "linear"


def test_a_point_outside_the_mesh_is_refused_by_name():
    with pytest.raises(ValueError, match="'outside'.*no element"):
        LatPerNodeReader().read(CASE, LAT, ReadRequest(names=("outside",), points={"outside": (-5000.0, 3500.0, 1500.0)}))


def test_the_per_event_layout_is_refused_by_name(tmp_path):
    case = tmp_path / "case"
    (case / "out").mkdir(parents=True)
    for name in ("slab.pts", "slab.elem"):
        (case / name).write_text((CASE / name).read_text())
    (case / "out" / "parameters.par").write_text((CASE / "out" / "parameters.par").read_text())
    (case / "out" / "vm_act-thresh.dat").write_text((CASE / "out" / "vm_act-thresh_per_event.dat").read_text())
    per_event = dataclasses.replace(LAT, path_pattern="out/vm_act-thresh.dat")
    with pytest.raises(ValueError, match=r"lats\[\]\.all = 1"):
        LatPerNodeReader().read(case, per_event, ReadRequest(names=("origin",), points={"origin": (0.0, 0.0, 0.0)}))
