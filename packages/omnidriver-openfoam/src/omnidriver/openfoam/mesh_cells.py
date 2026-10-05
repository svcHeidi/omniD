"""The cell centres and volumes of an OpenFOAM mesh, from its ``points``, ``faces``, ``owner`` and ``neighbour``."""

from __future__ import annotations

import math
import re
import sys
from array import array
from functools import lru_cache
from collections.abc import Sequence
from pathlib import Path

from omnidriver.openfoam.mesh_points import point_axes

_FORMAT = re.compile(r"\bformat\s+(\w+)\s*;")
_ARCH = re.compile(r'\barch\s+"(LSB|MSB);label=(32|64);scalar=(?:32|64)"')
_LIST_START = re.compile(rb"^\s*(\d+)\s*\(", re.MULTILINE)
_FACE = re.compile(rb"(\d+)\(([\d\s]*)\)")


class CellGeometry:
    """Each cell's centre (``x``, ``y``, ``z``) and volume, with a search of the cells near a point."""

    def __init__(self, x: list[float], y: list[float], z: list[float], volume: list[float]) -> None:
        self.x, self.y, self.z, self.volume = x, y, z, volume
        self._bins: dict[float, dict[tuple[int, int, int], list[int]]] = {}

    def _binned(self, size: float) -> dict[tuple[int, int, int], list[int]]:
        if size not in self._bins:
            bins: dict[tuple[int, int, int], list[int]] = {}
            for cell, key in enumerate(zip(self.x, self.y, self.z)):
                bins.setdefault((math.floor(key[0] / size), math.floor(key[1] / size), math.floor(key[2] / size)), []).append(cell)
            self._bins[size] = bins
        return self._bins[size]

    def _cells_within(self, point: Sequence[float], size: float, reach: int) -> list[tuple[float, int]]:
        """The ``(distance, cell)`` of every cell whose bin lies within ``reach`` bins of the point's."""
        bins = self._binned(size)
        ix, iy, iz = (math.floor(c / size) for c in point)
        found = []
        for i in range(ix - reach, ix + reach + 1):
            for j in range(iy - reach, iy + reach + 1):
                for k in range(iz - reach, iz + reach + 1):
                    for cell in bins.get((i, j, k), ()):
                        found.append((math.dist(point, (self.x[cell], self.y[cell], self.z[cell])), cell))
        return found

    def near(self, point: Sequence[float], radius: float) -> list[tuple[float, float]]:
        """The ``(distance, volume)`` of every cell whose centre lies within ``radius`` of ``point``."""
        return [(d, self.volume[cell]) for d, cell in self._cells_within(point, radius, 1) if d <= radius]

    def nearest(self, point: Sequence[float], scale: float, limit: int = 20) -> tuple[float, float] | None:
        """The ``(distance, volume)`` of the cell nearest ``point``, searching bins of size ``scale`` out to ``limit``
        bins, or ``None`` when no cell lies that near."""
        for reach in range(1, limit + 1):
            found = self._cells_within(point, scale, reach)
            if found and (best := min(found))[0] <= reach * scale:
                return best[0], self.volume[best[1]]
        return None


def _lists(path: Path, count: int) -> list[array]:
    """The first ``count`` counted lists of labels in ``path``, ascii or binary, as arrays."""
    data = path.read_bytes()
    header_end = data.find(b"}")
    header = data[:header_end + 1].decode("latin-1")
    layout = _FORMAT.search(header)
    if layout is None or layout.group(1) not in ("ascii", "binary"):
        raise ValueError(f"{path} is no ascii or binary list")
    arch = _ARCH.search(header)
    code = "i" if arch is None or arch.group(2) == "32" else "q"
    found: list[array] = []
    position = header_end
    for _ in range(count):
        start = _LIST_START.search(data, position)
        if start is None:
            raise ValueError(f"{path} holds fewer than {count} lists")
        size, begin = int(start.group(1)), start.end()
        values = array(code)
        if layout.group(1) == "binary":
            if arch is None:
                raise ValueError(f"{path} declares no arch")
            position = begin + size * values.itemsize
            if len(data) < position + 1 or data[position:position + 1] != b")":
                raise ValueError(f"{path} counts {size} labels but holds another number of bytes")
            values.frombytes(data[begin:position])
            if (arch.group(1) == "LSB") != (sys.byteorder == "little"):
                values.byteswap()
        else:
            position = data.index(b")", begin)
            values.extend(int(token) for token in data[begin:position].split())
            if len(values) != size:
                raise ValueError(f"{path} counts {size} labels but holds {len(values)}")
        found.append(values)
    return found


def _faces(path: Path) -> list[array]:
    """Each face's point labels: a binary file stores offsets then labels, an ascii one ``n(a b c)`` per face."""
    data = path.read_bytes()
    if b"faceCompactList" in data[:2000]:
        offsets, labels = _lists(path, 2)
        return [labels[offsets[i]:offsets[i + 1]] for i in range(len(offsets) - 1)]
    start = _LIST_START.search(data, data.find(b"}"))
    if start is None:
        raise ValueError(f"{path} is no list of faces")
    faces = [array("i", map(int, match.group(2).split())) for match in _FACE.finditer(data, start.end())]
    if len(faces) != int(start.group(1)):
        raise ValueError(f"{path} counts {start.group(1).decode()} faces but holds {len(faces)}")
    return faces


@lru_cache(maxsize=2)
def _geometry(directory: str, stamp: tuple[int, ...]) -> CellGeometry:
    mesh = Path(directory)
    px, py, pz = point_axes(mesh / "points")
    faces = _faces(mesh / "faces")
    (owner,) = _lists(mesh / "owner", 1)
    (neighbour,) = _lists(mesh / "neighbour", 1)
    if len(owner) != len(faces):
        raise ValueError(f"{mesh} has {len(faces)} faces but {len(owner)} owners")
    cells = max(max(owner), max(neighbour, default=-1)) + 1

    # OpenFOAM's primitiveMesh::makeCellCentresAndVols: faces are fans around their average point, a cell's centre
    # a volume-weighted mean of pyramids over an estimated centre.
    centre: list[tuple[float, float, float]] = []
    area: list[tuple[float, float, float]] = []
    for ids in faces:
        n = len(ids)
        ex, ey, ez = (sum(axis[i] for i in ids) / n for axis in (px, py, pz))
        sum_n, sum_a, sum_ac = [0.0] * 3, 0.0, [0.0] * 3
        for k in range(n):
            a, b = ids[k], ids[(k + 1) % n]
            ux, uy, uz = px[b] - px[a], py[b] - py[a], pz[b] - pz[a]
            vx, vy, vz = ex - px[a], ey - py[a], ez - pz[a]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            magnitude = (nx * nx + ny * ny + nz * nz) ** 0.5
            sum_n[0] += nx
            sum_n[1] += ny
            sum_n[2] += nz
            sum_a += magnitude
            sum_ac[0] += magnitude * (px[a] + px[b] + ex)
            sum_ac[1] += magnitude * (py[a] + py[b] + ey)
            sum_ac[2] += magnitude * (pz[a] + pz[b] + ez)
        if sum_a > 1e-300:
            centre.append((sum_ac[0] / (3 * sum_a), sum_ac[1] / (3 * sum_a), sum_ac[2] / (3 * sum_a)))
        else:
            centre.append((ex, ey, ez))
        area.append((0.5 * sum_n[0], 0.5 * sum_n[1], 0.5 * sum_n[2]))

    estimate = [[0.0, 0.0, 0.0] for _ in range(cells)]
    count = [0] * cells
    for face, cell in enumerate(owner):
        count[cell] += 1
        for axis in range(3):
            estimate[cell][axis] += centre[face][axis]
    for face, cell in enumerate(neighbour):
        count[cell] += 1
        for axis in range(3):
            estimate[cell][axis] += centre[face][axis]
    for cell in range(cells):
        estimate[cell] = [value / max(count[cell], 1) for value in estimate[cell]]

    moment = [[0.0, 0.0, 0.0] for _ in range(cells)]
    pyramid = [0.0] * cells
    for face in range(len(faces)):
        c, a = centre[face], area[face]
        for cell, sign in ((owner[face], 1.0), (neighbour[face] if face < len(neighbour) else -1, -1.0)):
            if cell < 0:
                continue
            e = estimate[cell]
            volume = sign * (a[0] * (c[0] - e[0]) + a[1] * (c[1] - e[1]) + a[2] * (c[2] - e[2]))
            pyramid[cell] += volume
            for axis in range(3):
                moment[cell][axis] += volume * (0.75 * c[axis] + 0.25 * e[axis])
    centres = [
        [moment[cell][axis] / pyramid[cell] if abs(pyramid[cell]) > 1e-300 else estimate[cell][axis] for cell in range(cells)]
        for axis in range(3)
    ]
    return CellGeometry(centres[0], centres[1], centres[2], [volume / 3 for volume in pyramid])


def cell_geometry(mesh_directory: Path) -> CellGeometry:
    """The centre and volume of every cell of the ``polyMesh`` in ``mesh_directory``, read once per version of its
    files. Raises ``ValueError`` for files that are no mesh, and ``OSError`` for one that is absent."""
    stamp = tuple(
        value for name in ("points", "faces", "owner", "neighbour")
        for value in (lambda status: (status.st_mtime_ns, status.st_size))((mesh_directory / name).stat())
    )
    return _geometry(str(mesh_directory.resolve()), stamp)
