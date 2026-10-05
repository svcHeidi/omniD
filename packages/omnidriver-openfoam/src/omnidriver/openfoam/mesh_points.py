"""The points of an OpenFOAM mesh and their extent, read from its ``points`` file."""

from __future__ import annotations

import re
import sys
from array import array
from functools import lru_cache
from collections.abc import Sequence
from pathlib import Path

Corner = tuple[float, float, float]

_FORMAT = re.compile(r"\bformat\s+(\w+)\s*;")
_LIST_START = re.compile(rb"^\s*(\d+)\s*\(", re.MULTILINE)
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _binary_axes(path: str, header: str, data: bytes, count: int) -> list[array]:
    arch = re.search(r'\barch\s+"(LSB|MSB);label=\d+;scalar=(\d+)"', header)
    if arch is None or arch.group(2) not in ("32", "64"):
        raise ValueError(f"{path} declares no arch of 32 or 64 bit scalars")
    values = array("f" if arch.group(2) == "32" else "d")
    width = values.itemsize * 3 * count
    if len(data) < width + 1 or data[width:width + 1] != b")":
        raise ValueError(f"{path} counts {count} points but holds another number of bytes")
    values.frombytes(data[:width])
    if (arch.group(1) == "LSB") != (sys.byteorder == "little"):
        values.byteswap()
    return [values[axis::3] for axis in range(3)]


@lru_cache(maxsize=4)
def _axes(path: str, stamp: tuple[int, int]) -> tuple[Sequence[float], Sequence[float], Sequence[float]]:
    data = Path(path).read_bytes()
    header_end = data.find(b"}")
    header = data[:header_end + 1].decode("latin-1")
    layout = _FORMAT.search(header)
    start = _LIST_START.search(data, header_end)
    if layout is None or layout.group(1) not in ("ascii", "binary") or start is None:
        raise ValueError(f"{path} is no ascii or binary list of points")
    count = int(start.group(1))
    if layout.group(1) == "binary":
        x, y, z = _binary_axes(path, header, data[start.end():], count)
        return x, y, z
    numbers = _NUMBER.findall(data[start.end():].decode("latin-1"))
    if len(numbers) != 3 * count:
        raise ValueError(f"{path} counts {count} points but holds {len(numbers)} numbers")
    return tuple(array("d", map(float, numbers[axis::3])) for axis in range(3))


def point_axes(points_file: Path) -> tuple[Sequence[float], Sequence[float], Sequence[float]]:
    """The x, y and z coordinates of the points in a ``polyMesh/points`` file, ascii or binary, read once per file
    version. Raises ``ValueError`` for a file that is no counted list of points."""
    status = points_file.stat()
    return _axes(str(points_file.resolve()), (status.st_mtime_ns, status.st_size))


def points_bounds(points_file: Path) -> tuple[Corner, Corner] | None:
    """The ``(minimum, maximum)`` corner of the points in a ``polyMesh/points`` file, ascii or binary, read once
    per file version, or ``None`` when the file is absent. Raises ``ValueError`` for a file that is no counted list
    of points."""
    if not points_file.is_file():
        return None
    x, y, z = point_axes(points_file)
    return (min(x), min(y), min(z)), (max(x), max(y), max(z))
