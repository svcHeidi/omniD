"""The LAT reader against the real binary: values at supplied points, in ms,
at the mesh nodes the solve used (F6, F16, F17, G4). Every file read here
was written by mesher and openCARP; no mesh is invented."""
from __future__ import annotations

import dataclasses

import pytest

from omnidriver.core.quantities import ReadRequest, read_quantities
from omnidriver.opencarp.lat_reader import LatPerNodeReader
from opencarp_native import niederer_run

pytestmark = pytest.mark.native_opencarp

CORNERS = {f"x{x}y{y}z{z}": (float(x), float(y), float(z)) for x in (0, 20000) for y in (0, 7000) for z in (0, 3000)}
CENTRE = {"centre": (10000.0, 3500.0, 1500.0)}


def test_the_slab_corners_and_centre_at_dx_500_match_g4(tmp_path):
    run = niederer_run(tmp_path, dx=500.0, tend=150.0)
    points = {**CORNERS, **CENTRE}
    quantities = {q.name: q for q in read_quantities(
        LatPerNodeReader(), run.case_root, run.lat_artifact, ReadRequest(names=tuple(points), points=points))}
    assert all(q.status == "evaluated" and q.unit == "ms" and q.sampling_rule == "node" for q in quantities.values())
    # at dx 500 every requested point is a node (F3: 41 x 15 x 7), so each is sampled where asked
    assert all(q.sampled_at == points[name] and q.sampled_at_unit == "um" for name, q in quantities.items())
    assert quantities["x0y0z0"].value == pytest.approx(1.355, abs=5e-4)             # G4: P1, 1.355 ms
    assert quantities["x20000y7000z3000"].value == pytest.approx(126.45, abs=5e-3)  # G4: P8, 126.45 ms
    assert quantities["x0y0z0"].value < quantities["centre"].value < quantities["x20000y7000z3000"].value


def test_a_node_never_reached_is_not_reached_never_minus_one(tmp_path):
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
    far = {"far": (20000.0, 7000.0, 3000.0)}
    (quantity,) = read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                  ReadRequest(names=("far",), points=far))
    assert (quantity.status, quantity.value) == ("not_reached", None)


def test_a_point_equidistant_from_nodes_is_refused_by_name(tmp_path):
    """At dx 1000 the centre (10000, 3500, 1500) um lies midway between nodes
    on two axes (21 x 8 x 4 points, F16's run)."""
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0)
    with pytest.raises(ValueError, match="'centre'.*equidistant"):
        LatPerNodeReader().read(run.case_root, run.lat_artifact, ReadRequest(names=("centre",), points=CENTRE))


def test_the_per_event_layout_is_refused_by_name(tmp_path):
    """F17: with lats[0].all = 1 the declared per-node file is absent, and the
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
