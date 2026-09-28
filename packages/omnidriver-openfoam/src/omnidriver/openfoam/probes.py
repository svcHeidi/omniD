"""OpenFOAM's ``probes`` function-object output: file layout, with no field
meaning. Verified against OpenFOAM v2412's own
``src/sampling/probes/probes.C``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

Point = tuple[float, float, float]

# One file per field at postProcessing/<function>/<startTime>/<field>: a
# `# Probe <k> (<x> <y> <z>)` header per configured location (`# Not Found`
# appended when no cell contains it), a `# Time <k>...` line naming each
# column's probe, then one row per time: time + one value per probe.
_PROBE = re.compile(r"^# Probe (\d+) \(([^()]*)\)(.*)$")
_NOT_FOUND = "# Not Found"


@dataclass(frozen=True)
class ProbeSeries:
    """``rows[i]`` holds one value per probe, in ``locations`` order, at
    ``times[i]``. ``not_found`` marks indices OpenFOAM wrote as
    ``# Not Found``, holding its -VGREAT placeholder rather than a sample.
    """

    locations: tuple[tuple[int, Point], ...]
    times: tuple[float, ...]
    rows: tuple[tuple[float, ...], ...]
    not_found: frozenset[int]


def parse_probe_series(text: str, *, source: str) -> ProbeSeries:
    """Read one scalar probe file. Refuses, naming ``source`` and why: no
    probe lines, a repeated probe index, an annotation other than ``# Not
    Found``, a ``# Time`` header that does not name every probe in order, a
    row whose column count is not 1 + probes, a vector or tensor value, and
    no data rows."""
    locations: list[tuple[int, Point]] = []
    not_found: set[int] = set()
    columns: list[int] | None = None
    times: list[float] = []
    rows: list[tuple[float, ...]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        where = f"{source} line {number}"
        probe = _PROBE.match(stripped)
        if probe:
            index = int(probe.group(1))
            if any(index == seen for seen, _ in locations):
                raise ValueError(f"{where} names probe {index} twice")
            coordinates = probe.group(2).split()
            if len(coordinates) != 3:
                raise ValueError(f"{where}: probe {index} has {len(coordinates)} coordinates, expected x y z")
            annotation = probe.group(3).strip()
            if annotation == _NOT_FOUND:
                not_found.add(index)
            elif annotation:
                raise ValueError(f"{where}: probe {index} carries {annotation!r}; only {_NOT_FOUND!r} is understood")
            locations.append((index, (float(coordinates[0]), float(coordinates[1]), float(coordinates[2]))))
            continue
        if stripped.startswith("# Time"):
            columns = [int(token) for token in stripped[len("# Time"):].split()]
            continue
        if stripped.startswith("#"):
            continue
        if "(" in stripped or ")" in stripped:
            # OpenFOAM writes vector/tensor probe values in parentheses (probes.C).
            raise ValueError(f"{where} holds a vector or tensor value; this parser reads scalar probe files only")
        if not locations:
            raise ValueError(f"{source} has no '# Probe <k> (<x> <y> <z>)' lines before its data")
        expected = [index for index, _ in locations]
        if columns != expected:
            raise ValueError(
                f"{source}: its '# Time' header names probes {columns}, but its '# Probe' lines are {expected}; "
                "a column cannot be matched to a probe"
            )
        fields = stripped.split()
        if len(fields) != 1 + len(locations):
            raise ValueError(f"{where} has {len(fields)} columns, expected {1 + len(locations)} (time + one per probe)")
        values = tuple(float(field) for field in fields)
        times.append(values[0])
        rows.append(values[1:])
    if not locations:
        raise ValueError(f"{source} has no '# Probe <k> (<x> <y> <z>)' lines")
    if not rows:
        raise ValueError(f"{source} has no data rows")
    return ProbeSeries(tuple(locations), tuple(times), tuple(rows), frozenset(not_found))


def interpolation_scheme(case_root: Path, probe_path: str) -> str:
    """The ``interpolationScheme`` of the ``probes`` function that writes
    ``probe_path`` (``postProcessing/<function>/<instance>/<field>``), read
    from the case's own ``system/<function>`` -- one source of truth, never
    restated. OpenFOAM's own default, ``cell``, applies when the key is
    absent (``probes.C``'s ``samplePointScheme_("cell")``)."""
    parts = PurePosixPath(probe_path).parts
    if len(parts) != 4 or parts[0] != "postProcessing":
        raise ValueError(f"{probe_path!r} is not a probes file, postProcessing/<function>/<instance>/<field>")
    from foamlib import FoamFile

    return str(FoamFile(Path(case_root) / "system" / parts[1]).get("interpolationScheme", "cell"))
