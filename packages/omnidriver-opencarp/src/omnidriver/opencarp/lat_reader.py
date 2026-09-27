"""Activation times from openCARP's per-node LAT file, at points an agent supplies.

Each fact below comes from the real binary (docs/solver-learning/opencarp.md):
- ``init_acts_<lats[].ID>-thresh.dat`` with ``lats[].all = 0``: one value per
  mesh point, in point order, ``-1`` for never activated, in ms (F6, G4). With
  ``all = 1`` openCARP writes a two-column per-event file instead (F17),
  which this reader refuses;
- the mesh the solve used is ``meshname`` as the solver recorded it in
  ``<simID>/parameters.par`` (D5, F16), relative to the case root, which is
  the solve step's working directory (F5);
- ``<meshname>.pts`` holds a point count, then ``x y z`` per point, in µm (F3);
- ``<meshname>.elem`` holds an element count, then ``Tt n0 n1 n2 n3 tag`` per
  line: linear tetrahedra, openCARP's only element type for this mesh.

Sampling rule ``linear``: the barycentric interpolation of the four corner
nodes' LAT over the tetrahedron containing the point -- the FE solution
itself, defined and continuous everywhere in the mesh, including at a face,
edge or node shared by several elements, so no tie needs a rule. The point
requested is reported as ``sampled_at`` unchanged (the offset is always 0).
A point in no element is refused by name. Points come from the agent's
comparison request, already converted to µm by core. This reader orients
nothing: openCARP's frame is whatever the mesh says.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.quantities import RawSample, ReadRequest

from .par_format import read_raw, unquote

LAT_FORMAT = "opencarp_lat_per_node"

Point = tuple[float, float, float]
Tet = tuple[int, int, int, int]

_BARYCENTRIC_TOL = 1e-6


def _mesh_name(parameters: Path) -> str:
    try:
        text = parameters.read_text()
    except OSError as exc:
        raise ValueError(f"cannot read {parameters}, where openCARP records the mesh a solve used (F16): {exc}") from exc
    raw = read_raw(text, "meshname")
    if raw is None:
        raise ValueError(f"{parameters} records no meshname (F16)")
    return unquote(raw)


def _read_pts(path: Path) -> list[Point]:
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


def _read_elem(path: Path) -> list[Tet]:
    try:
        rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    except OSError as exc:
        raise ValueError(f"cannot read the mesh elements {path}: {exc}") from exc
    if not rows or len(rows[0]) != 1:
        raise ValueError(f"{path} does not start with an element count")
    count = int(rows[0][0])
    tets = []
    for number, row in enumerate(rows[1:], start=2):
        if len(row) != 6 or row[0] != "Tt":
            raise ValueError(f"{path} line {number} is not a linear tetrahedron (Tt n0 n1 n2 n3 tag)")
        tets.append((int(row[1]), int(row[2]), int(row[3]), int(row[4])))
    if len(tets) != count:
        raise ValueError(f"{path} declares {count} elements but lists {len(tets)}")
    return tets


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


def _barycentric(points: list[Point], tet: Tet, target: Point) -> tuple[float, float, float, float] | None:
    """``target``'s barycentric weights over ``tet``, or ``None`` if it lies
    outside it (beyond ``_BARYCENTRIC_TOL``, so a face/edge/node is inside)."""
    v0, v1, v2, v3 = (points[n] for n in tet)
    ax, ay, az = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
    bx, by, bz = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
    cx, cy, cz = v3[0] - v0[0], v3[1] - v0[1], v3[2] - v0[2]
    dx, dy, dz = target[0] - v0[0], target[1] - v0[1], target[2] - v0[2]
    det = ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    if det == 0:
        return None
    det1 = dx * (by * cz - bz * cy) - dy * (bx * cz - bz * cx) + dz * (bx * cy - by * cx)
    det2 = ax * (dy * cz - dz * cy) - ay * (dx * cz - dz * cx) + az * (dx * cy - dy * cx)
    det3 = ax * (by * dz - bz * dy) - ay * (bx * dz - bz * dx) + az * (bx * dy - by * dx)
    w1, w2, w3 = det1 / det, det2 / det, det3 / det
    w0 = 1.0 - w1 - w2 - w3
    weights = (w0, w1, w2, w3)
    if all(-_BARYCENTRIC_TOL <= w <= 1.0 + _BARYCENTRIC_TOL for w in weights):
        return weights
    return None


class _TetLocator:
    """Finds the tetrahedron containing a point, from a grid of nearby tets
    (bucketed by centroid) rather than a scan of all of them -- the search
    that keeps this usable at 2.1 M tets (Δx 0.1 mm)."""

    def __init__(self, points: list[Point], tets: list[Tet]) -> None:
        self._points = points
        self._tets = tets
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        self._origin = (min(xs), min(ys), min(zs))
        extent = max(max(xs) - self._origin[0], max(ys) - self._origin[1], max(zs) - self._origin[2]) or 1.0
        axis_cells = max(1, round(len(tets) ** (1 / 3)))
        self._cell_size = extent / axis_cells
        self._grid: dict[tuple[int, int, int], list[int]] = {}
        for index, tet in enumerate(tets):
            v0, v1, v2, v3 = (points[n] for n in tet)
            centroid = tuple((v0[i] + v1[i] + v2[i] + v3[i]) / 4.0 for i in range(3))
            self._grid.setdefault(self._cell_of(centroid), []).append(index)
        ixs = [k[0] for k in self._grid]
        iys = [k[1] for k in self._grid]
        izs = [k[2] for k in self._grid]
        self._bounds = (min(ixs), max(ixs), min(iys), max(iys), min(izs), max(izs))
        x0, x1, y0, y1, z0, z1 = self._bounds
        self._max_radius = max(x1 - x0, y1 - y0, z1 - z0) + 1

    def _cell_of(self, point: Point) -> tuple[int, int, int]:
        return tuple(int((point[i] - self._origin[i]) / self._cell_size) for i in range(3))

    def _clamped(self, cell: tuple[int, int, int]) -> tuple[int, int, int]:
        x0, x1, y0, y1, z0, z1 = self._bounds
        return (min(max(cell[0], x0), x1), min(max(cell[1], y0), y1), min(max(cell[2], z0), z1))

    def locate(self, target: Point) -> tuple[int, tuple[float, float, float, float]] | None:
        cx, cy, cz = self._clamped(self._cell_of(target))
        tried: set[int] = set()
        for radius in range(self._max_radius + 1):
            candidates: set[int] = set()
            for ix in range(cx - radius, cx + radius + 1):
                for iy in range(cy - radius, cy + radius + 1):
                    for iz in range(cz - radius, cz + radius + 1):
                        candidates.update(self._grid.get((ix, iy, iz), ()))
            for tet_index in candidates - tried:
                tried.add(tet_index)
                weights = _barycentric(self._points, self._tets[tet_index], target)
                if weights is not None:
                    return tet_index, weights
        return None


class LatPerNodeReader:
    value_unit = "ms"
    sentinels = frozenset({-1.0})
    sampling_rule = "linear"
    coordinate_unit = "um"
    takes_points = True

    def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
        case_root = Path(case_root)
        lat_path = case_root / artifact.path_pattern
        mesh_name = _mesh_name(lat_path.parent / "parameters.par")
        points = _read_pts(case_root / f"{mesh_name}.pts")
        tets = _read_elem(case_root / f"{mesh_name}.elem")
        values = _read_lat(lat_path, point_count=len(points))
        locator = _TetLocator(points, tets)
        samples = []
        for name in request.names:
            target = request.points[name]
            located = locator.locate(target)
            if located is None:
                raise ValueError(f"point {name!r} at {list(target)} um lies in no element of {mesh_name!r}")
            tet_index, weights = located
            corners = [values[node] for node in tets[tet_index]]
            sentinel = next((v for v in corners if v in self.sentinels), None)
            value = sentinel if sentinel is not None else sum(w * v for w, v in zip(weights, corners))
            samples.append(RawSample(name=name, value=value, sampled_at=target))
        return tuple(samples)
