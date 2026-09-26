"""Activation times from openCARP's per-node LAT file, at points an agent supplies.

Each fact below comes from the real binary (docs/solver-learning/opencarp.md):
- ``init_acts_<lats[].ID>-thresh.dat`` with ``lats[].all = 0``: one value per
  mesh point, in point order, ``-1`` for never activated, in ms (F6, G4). With
  ``all = 1`` openCARP writes a two-column per-event file instead (F17),
  which this reader refuses;
- the mesh the solve used is ``meshname`` as the solver recorded it in
  ``<simID>/parameters.par`` (D5, F16), relative to the case root, which is
  the solve step's working directory (F5);
- ``<meshname>.pts`` holds a point count, then ``x y z`` per point, in µm (F3).

Sampling rule ``node``: the mesh point nearest each supplied point, whose
coordinates are reported as ``sampled_at``. A tie is refused by name.
Points come from the agent's comparison request, already converted to µm
by core. This reader orients nothing: openCARP's frame is whatever the mesh
says.
"""
from __future__ import annotations

import math
from pathlib import Path

from omnidriver.core.quantities import RawSample, ReadRequest

from .par_format import read_raw, unquote

LAT_FORMAT = "opencarp_lat_per_node"


def _mesh_name(parameters: Path) -> str:
    try:
        text = parameters.read_text()
    except OSError as exc:
        raise ValueError(f"cannot read {parameters}, where openCARP records the mesh a solve used (F16): {exc}") from exc
    raw = read_raw(text, "meshname")
    if raw is None:
        raise ValueError(f"{parameters} records no meshname (F16)")
    return unquote(raw)


def _read_pts(path: Path) -> list[tuple[float, float, float]]:
    try:
        rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    except OSError as exc:
        raise ValueError(f"cannot read the mesh points {path}: {exc}") from exc
    if not rows or len(rows[0]) != 1:
        raise ValueError(f"{path} does not start with a point count (F3)")
    count = int(rows[0][0])
    points = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != 3:
            raise ValueError(f"{path} line {number} has {len(row)} fields, expected x y z")
        points.append((float(row[0]), float(row[1]), float(row[2])))
    if len(points) != count:
        raise ValueError(f"{path} declares {count} points but lists {len(points)}")
    return points


def _read_lat(path: Path, *, point_count: int) -> list[float]:
    rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    if any(len(row) != 1 for row in rows):
        raise ValueError(
            f"{path} has more than one column: openCARP's per-event layout (lats[].all = 1, F17), "
            f"not one value per node; set nversion.par:lats[0].all to false"
        )
    if len(rows) != point_count:
        raise ValueError(f"{path} has {len(rows)} values for a mesh of {point_count} points (F6: one per node)")
    return [float(row[0]) for row in rows]


def _nearest(points: list[tuple[float, float, float]], target: tuple[float, float, float], *, name: str) -> int:
    distances = [math.dist(point, target) for point in points]
    best = min(distances)
    tied = [index for index, distance in enumerate(distances) if distance == best]
    if len(tied) > 1:
        raise ValueError(
            f"point {name!r} at {list(target)} um is equidistant ({best} um) from nodes "
            f"{[list(points[i]) for i in tied[:8]]}; supply a point nearer one node"
        )
    return tied[0]


class LatPerNodeReader:
    value_unit = "ms"
    sentinels = frozenset({-1.0})
    sampling_rule = "node"
    coordinate_unit = "um"
    takes_points = True

    def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
        case_root = Path(case_root)
        lat_path = case_root / artifact.path_pattern
        points = _read_pts(case_root / f"{_mesh_name(lat_path.parent / 'parameters.par')}.pts")
        values = _read_lat(lat_path, point_count=len(points))
        samples = []
        for name in request.names:
            index = _nearest(points, request.points[name], name=name)
            samples.append(RawSample(name=name, value=values[index], sampled_at=points[index]))
        return tuple(samples)
