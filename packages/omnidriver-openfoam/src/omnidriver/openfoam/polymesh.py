"""An OpenFOAM mesh read from its ``polyMesh`` files: the extent of its points, and the cells around given locations."""

from __future__ import annotations

import math
import re
import sys
from array import array
from collections.abc import Sequence
from functools import lru_cache
from itertools import accumulate, chain, compress, repeat
from operator import gt, or_
from pathlib import Path
from typing import NamedTuple

Corner = tuple[float, float, float]

_HEADER = re.compile(rb"FoamFile\s*\{(.*?)\}", re.DOTALL)
_ENTRY = re.compile(r'(\w+)\s+("[^"]*"|[^;]*?)\s*;')
_ARCH = re.compile(r"(LSB|MSB);label=(32|64);scalar=(32|64)")
_LIST_START = re.compile(rb"^\s*(\d+)\s*\(", re.MULTILINE)
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# A face is "n(a b c)", and a long one "n\n(\na\nb\n...)": OpenFOAM breaks a list of more than ten entries across lines.
_FACE = re.compile(rb"(\d+)\s*\(([\d\s]*)\)")


class _File(NamedTuple):
    path: Path
    data: bytes
    header: dict[str, str]
    start: int
    binary: bool

    @property
    def arch(self) -> tuple[str, int, int] | None:
        match = _ARCH.search(self.header.get("arch", ""))
        return (match.group(1), int(match.group(2)), int(match.group(3))) if match else None


def _require(path: Path) -> Path:
    """``path``; ``FileNotFoundError`` when absent and ``ValueError`` when only its compressed form is there."""
    if not path.is_file():
        if path.with_name(path.name + ".gz").is_file():
            raise ValueError(f"{path}.gz is compressed, and omniD reads ascii and binary files")
        raise FileNotFoundError(path)
    return path


def _open(path: Path, what: str) -> _File:
    """``path``, with the keys of its ``FoamFile`` header. Raises ``FileNotFoundError`` for an absent file and
    ``ValueError`` for a compressed one or one that is neither ascii nor binary."""
    data = _require(path).read_bytes()
    block = _HEADER.search(data, 0, 8192)
    header = {key: value.strip('"') for key, value in _ENTRY.findall(block.group(1).decode("latin-1"))} if block else {}
    if header.get("format") not in ("ascii", "binary"):
        raise ValueError(f"{path} is no ascii or binary list of {what}")
    return _File(path, data, header, block.end(), header["format"] == "binary")


def _next_list(file: _File, position: int) -> tuple[int, int]:
    """The element count of the list starting after ``position`` and the offset just after its ``(``."""
    start = _LIST_START.search(file.data, position)
    if start is None:
        raise ValueError(f"{file.path} holds no counted list")
    return int(start.group(1)), start.end()


def _binary_values(file: _File, count: int, per: int, begin: int, code: str, noun: str) -> tuple[array, int]:
    """``count`` items of ``per`` numbers each of type ``code``, from ``begin``, and where they end."""
    if file.arch is None:
        raise ValueError(f"{file.path} declares no arch of 32 or 64 bit scalars")
    values = array(code)
    end = begin + count * per * values.itemsize
    if len(file.data) < end + 1 or file.data[end:end + 1] != b")":
        raise ValueError(f"{file.path} counts {count} {noun} but holds another number of bytes")
    values.frombytes(file.data[begin:end])
    if (file.arch[0] == "LSB") != (sys.byteorder == "little"):
        values.byteswap()
    return values, end


def _labels(file: _File, position: int = 0) -> tuple[array, int]:
    """The next counted list of labels after ``position`` and where it ends."""
    count, begin = _next_list(file, position or file.start)
    if file.binary:
        return _binary_values(file, count, 1, begin, "i" if file.arch and file.arch[1] == 32 else "q", "labels")
    end = file.data.index(b")", begin)
    values = array("i", map(int, file.data[begin:end].split()))
    if len(values) != count:
        raise ValueError(f"{file.path} counts {count} labels but holds {len(values)}")
    return values, end


@lru_cache(maxsize=4)
def _axes(path: str, stamp: tuple[int, int]) -> tuple[Sequence[float], Sequence[float], Sequence[float]]:
    file = _open(Path(path), "points")
    count, begin = _next_list(file, file.start)
    if file.binary:
        values, _ = _binary_values(file, count, 3, begin, "f" if file.arch and file.arch[2] == 32 else "d", "points")
        return values[0::3], values[1::3], values[2::3]
    numbers = _NUMBER.findall(file.data[begin:].decode("latin-1"))
    if len(numbers) != 3 * count:
        raise ValueError(f"{path} counts {count} points but holds {len(numbers)} numbers")
    return tuple(array("d", map(float, numbers[axis::3])) for axis in range(3))  # type: ignore[return-value]


def point_axes(points_file: Path) -> tuple[Sequence[float], Sequence[float], Sequence[float]]:
    """The x, y and z coordinates of the points in a ``polyMesh/points`` file, ascii or binary, read once per file
    version. Raises ``ValueError`` for a file that is no counted list of points."""
    status = points_file.stat()
    return _axes(str(points_file.resolve()), (status.st_mtime_ns, status.st_size))


def points_bounds(points_file: Path) -> tuple[Corner, Corner] | None:
    """The ``(minimum, maximum)`` corner of the points in a ``polyMesh/points`` file, ascii or binary, read once
    per file version, or ``None`` when the file is absent. Raises ``ValueError`` for a file that is no counted list
    of points, or is compressed."""
    try:
        _require(points_file)
    except FileNotFoundError:
        return None
    x, y, z = point_axes(points_file)
    return (min(x), min(y), min(z)), (max(x), max(y), max(z))


def _faces(mesh: Path) -> tuple[array, array]:
    """The point labels of every face, flat, and the offset where each face starts (one more than the faces)."""
    file = _open(mesh / "faces", "faces")
    if file.header.get("class") == "faceCompactList":
        offsets, end = _labels(file)
        labels, _ = _labels(file, end)
        return labels, offsets
    count, begin = _next_list(file, file.start)
    labels, offsets = array("i"), array("i", [0])
    for face in _FACE.finditer(file.data, begin):
        ids = face.group(2).split()
        if len(ids) != int(face.group(1)):
            raise ValueError(f"{file.path} has a face of {len(ids)} points counted as {face.group(1).decode()}")
        labels.extend(map(int, ids))
        offsets.append(len(labels))
    if len(offsets) - 1 != count:
        raise ValueError(f"{file.path} counts {count} faces but holds {len(offsets) - 1}")
    return labels, offsets


#: The most faces of the cells around the locations whose geometry is computed, in pure Python (about 10 us a
#: face and 100 bytes), so a mesh of millions of cells with a location everywhere is refused, not read for minutes.
FACE_LIMIT = 600_000


class Cell(NamedTuple):
    """A cell near a location: its distance from it, its volume and its label; tuples sort nearest first."""

    distance: float
    volume: float
    label: int


class Surroundings(NamedTuple):
    """The cells with a centre within a radius of a location, nearest first, and the nearest cell that was examined
    (the first of them when there are any)."""

    within: list[Cell]
    nearest: Cell | None


def _near_flags(points: Sequence[Sequence[float]], locations: Sequence[Sequence[float]], reach: float) -> bytearray:
    """Which points lie within ``reach`` of some location."""
    def key(x: float, y: float, z: float) -> tuple[int, int, int]:
        return math.floor(x / reach), math.floor(y / reach), math.floor(z / reach)

    placed: dict[tuple[int, int, int], list[Sequence[float]]] = {}
    for location in locations:
        placed.setdefault(key(*location), []).append(location)
    around: dict[tuple[int, int, int], list[Sequence[float]]] = {}
    px, py, pz = points
    flags = bytearray(len(px))
    for point, (x, y, z) in enumerate(zip(px, py, pz)):
        here = key(x, y, z)
        if here not in around:
            around[here] = [
                location for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)
                for location in placed.get((here[0] + i, here[1] + j, here[2] + k), ())
            ]
        for lx, ly, lz in around[here]:
            if (x - lx) ** 2 + (y - ly) ** 2 + (z - lz) ** 2 <= reach * reach:
                flags[point] = 1
                break
    return flags


def _geometry(
    points: Sequence[Sequence[float]], faces: Sequence[int], labels: array, offsets: array, owner: array,
    neighbour: array, wanted: bytearray,
) -> dict[int, tuple[float, float, float, float]]:
    """``(x, y, z, volume)`` of each cell flagged in ``wanted``, by OpenFOAM's ``primitiveMesh::makeCellCentresAndVols``:
    a face is a fan around its average point, a cell's centre a volume-weighted mean of the pyramids from an
    estimated centre over its faces. ``faces`` holds every face of those cells, and their geometry is kept flat."""
    px, py, pz = points
    cells = len(wanted)
    fc, fa = array("d", bytes(8 * 3 * len(faces))), array("d", bytes(8 * 3 * len(faces)))
    estimate, count = array("d", bytes(8 * 3 * cells)), array("i", bytes(4 * cells))
    internal = len(neighbour)
    for position, face in enumerate(faces):
        ids = labels[offsets[face]:offsets[face + 1]]
        n = len(ids)
        if n == 3:
            a, b, c = ids
            ux, uy, uz, vx, vy, vz = px[b] - px[a], py[b] - py[a], pz[b] - pz[a], px[c] - px[a], py[c] - py[a], pz[c] - pz[a]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            cx, cy, cz = (px[a] + px[b] + px[c]) / 3, (py[a] + py[b] + py[c]) / 3, (pz[a] + pz[b] + pz[c]) / 3
        else:
            ex, ey, ez = (sum(axis[i] for i in ids) / n for axis in (px, py, pz))
            nx = ny = nz = total = ax = ay = az = 0.0
            for k in range(n):
                a, b = ids[k], ids[(k + 1) % n]
                ux, uy, uz = px[b] - px[a], py[b] - py[a], pz[b] - pz[a]
                vx, vy, vz = ex - px[a], ey - py[a], ez - pz[a]
                gx, gy, gz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                magnitude = (gx * gx + gy * gy + gz * gz) ** 0.5
                nx, ny, nz, total = nx + gx, ny + gy, nz + gz, total + magnitude
                ax += magnitude * (px[a] + px[b] + ex)
                ay += magnitude * (py[a] + py[b] + ey)
                az += magnitude * (pz[a] + pz[b] + ez)
            cx, cy, cz = (ax / (3 * total), ay / (3 * total), az / (3 * total)) if total > 1e-300 else (ex, ey, ez)
        fc[3 * position], fc[3 * position + 1], fc[3 * position + 2] = cx, cy, cz
        fa[3 * position], fa[3 * position + 1], fa[3 * position + 2] = 0.5 * nx, 0.5 * ny, 0.5 * nz
        for cell in (owner[face], neighbour[face] if face < internal else -1):
            if cell >= 0 and wanted[cell]:
                estimate[3 * cell] += cx
                estimate[3 * cell + 1] += cy
                estimate[3 * cell + 2] += cz
                count[cell] += 1
    moment, pyramid = array("d", bytes(8 * 3 * cells)), array("d", bytes(8 * cells))
    for position, face in enumerate(faces):
        cx, cy, cz = fc[3 * position], fc[3 * position + 1], fc[3 * position + 2]
        ax, ay, az = fa[3 * position], fa[3 * position + 1], fa[3 * position + 2]
        for cell, sign in ((owner[face], 1.0), (neighbour[face] if face < internal else -1, -1.0)):
            if cell < 0 or not wanted[cell]:
                continue
            ex, ey, ez = (estimate[3 * cell + i] / count[cell] for i in range(3))
            volume = sign * (ax * (cx - ex) + ay * (cy - ey) + az * (cz - ez))
            pyramid[cell] += volume
            moment[3 * cell] += volume * (0.75 * cx + 0.25 * ex)
            moment[3 * cell + 1] += volume * (0.75 * cy + 0.25 * ey)
            moment[3 * cell + 2] += volume * (0.75 * cz + 0.25 * ez)
    found = {}
    for cell in compress(range(cells), wanted):
        if not count[cell]:
            continue
        total = pyramid[cell]
        centre = (
            tuple(moment[3 * cell + i] / total for i in range(3)) if abs(total) > 1e-300
            else tuple(estimate[3 * cell + i] / count[cell] for i in range(3))
        )
        found[cell] = (*centre, total / 3)
    return found  # type: ignore[return-value]


@lru_cache(maxsize=2)
def _surroundings(
    directory: str, stamp: tuple[int, ...], locations: tuple[Corner, ...], radius: float,
) -> tuple[Surroundings, ...]:
    mesh = Path(directory)
    px, py, pz = point_axes(mesh / "points")
    labels, offsets = _faces(mesh)
    owner, _ = _labels(_open(mesh / "owner", "labels"))
    neighbour, _ = _labels(_open(mesh / "neighbour", "labels"))
    faces = len(offsets) - 1
    if len(owner) != faces:
        raise ValueError(f"{mesh} has {faces} faces but {len(owner)} owners")

    # A cell with a centre within the radius of a location has every point within the radius plus its own size,
    # which the solver keeps below the radius (pvjMapper refuses a smaller one) for the cell nearest a junction.
    reach = 2.5 * radius
    near = _near_flags((px, py, pz), locations, reach)
    cumulative = array("i", [0])
    cumulative.extend(accumulate(map(near.__getitem__, labels)))
    touches = map(gt, map(cumulative.__getitem__, offsets[1:]), map(cumulative.__getitem__, offsets[:-1]))
    wanted = bytearray(max(max(owner), max(neighbour, default=-1)) + 1)
    for face in compress(range(faces), touches):
        wanted[owner[face]] = 1
        if face < len(neighbour):
            wanted[neighbour[face]] = 1
    beside = chain(map(wanted.__getitem__, neighbour), repeat(0))
    chosen = list(compress(range(faces), map(or_, map(wanted.__getitem__, owner), beside)))
    if len(chosen) > FACE_LIMIT:
        raise ValueError(
            f"the cells around the locations have {len(chosen)} faces, more than the {FACE_LIMIT} omniD reads "
            "without a numerical library"
        )
    cells = _geometry((px, py, pz), chosen, labels, offsets, owner, neighbour, wanted)

    def binned(size: float) -> dict[tuple[int, int, int], list[int]]:
        bins: dict[tuple[int, int, int], list[int]] = {}
        for cell, (x, y, z, _) in cells.items():
            bins.setdefault((math.floor(x / size), math.floor(y / size), math.floor(z / size)), []).append(cell)
        return bins

    def around(bins: dict[tuple[int, int, int], list[int]], size: float, location: Corner) -> list[Cell]:
        ix, iy, iz = (math.floor(c / size) for c in location)
        return sorted(
            Cell(math.dist(location, cells[cell][:3]), cells[cell][3], cell)
            for i in range(ix - 1, ix + 2) for j in range(iy - 1, iy + 2) for k in range(iz - 1, iz + 2)
            for cell in bins.get((i, j, k), ())
        )

    fine, coarse = binned(radius), binned(reach)
    found = []
    for location in locations:
        within = [cell for cell in around(fine, radius, location) if cell.distance <= radius]
        nearest = within[0] if within else next(iter(around(coarse, reach, location)), None)
        found.append(Surroundings(within, nearest))
    return tuple(found)


def cells_around(mesh_directory: Path, locations: Sequence[Corner], radius: float) -> tuple[Surroundings, ...]:
    """For each location, the cells of the ``polyMesh`` in ``mesh_directory`` whose centre lies within ``radius`` of
    it, and the nearest of the cells examined (those with a point near some location, so a cell no cell of which
    lies within about three radii is not among them). Only those cells' geometry is computed, by OpenFOAM's own
    formulas, and at most ``FACE_LIMIT`` faces of them. Raises ``ValueError`` for files that are no mesh, are
    compressed, or hold more such cells than that, and ``FileNotFoundError`` for an absent one."""
    stamp = tuple(
        value for name in ("points", "faces", "owner", "neighbour")
        for value in (lambda status: (status.st_mtime_ns, status.st_size))(_require(mesh_directory / name).stat())
    )
    return _surroundings(str(mesh_directory.resolve()), stamp, tuple(tuple(map(float, point)) for point in locations), radius)
