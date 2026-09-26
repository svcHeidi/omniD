"""OpenFOAM's ``probes`` function-object output: its layout, with no field meaning.

Each fact comes from OpenFOAM v2412 itself (``src/sampling/probes/probes.C``,
``probes::prepare``) and a real run (docs/solver-learning/cardiacfoam.md,
section Q):

- one file per field at ``postProcessing/<function>/<startTime>/<field>``;
- a header of ``# Probe <k> (<x> <y> <z>)`` lines, one per configured
  location, echoing the location *as configured* -- ``# Not Found`` is
  appended when no cell contains it (Q6), and OpenFOAM then writes -VGREAT
  in its column, a number, not a statement, so the flag is kept here;
- a ``# Time <k>...`` line naming each column's probe;
- one row per written time: the time, then one value per probe. A vector or
  tensor value is written in parentheses (Q5), and refused here: this parser
  reads scalars only.

Where OpenFOAM sampled (the containing cell, with no ``interpolationScheme``)
is not in the file. What says so is a second probe of the cell-centre
components ``writeCellCentres`` writes (:data:`CELL_CENTRE_FIELDS`), run
through the same function, so through the same cell search: Q3/Q4 found its
values equal to the ``C`` entry of the very cell ``probes`` reports under
``-debug-switch probes=1``. :func:`probes_function_with_fields` and
:func:`sibling_probe_files` spell that second probe's ``-func`` argument and
output files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence

Point = tuple[float, float, float]

#: ``writeCellCentres``'s component fields (``writeCellCentres::write``:
#: ``mesh_.C().name() + vector::componentNames[i]``), scalar, so the parser
#: below reads them.
CELL_CENTRE_FIELDS: tuple[str, str, str] = ("Cx", "Cy", "Cz")

_PROBE = re.compile(r"^# Probe (\d+) \(([^()]*)\)(.*)$")
_NOT_FOUND = "# Not Found"


@dataclass(frozen=True)
class ProbeSeries:
    """``locations``: ``(index, configured location)`` in header order.
    ``rows[i]`` holds one value per probe, in ``locations`` order, at
    ``times[i]``. ``not_found``: the indices OpenFOAM marked ``# Not Found``,
    whose values are OpenFOAM's -VGREAT placeholder, never a sample."""

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


def probes_function_with_fields(function: str, fields: Sequence[str]) -> str:
    """The ``postProcess -func`` argument that re-runs ``function`` on
    ``fields``. OpenFOAM names the function object -- and so its output
    directory -- after this whole argument (``functionObjectList::
    readFunctionObject``: ``word::validate(funcNameArgs)``, which keeps the
    parentheses and commas and drops whitespace, so none is written)."""
    return f"{function}({','.join(fields)})"


def sibling_probe_files(probe_path: str, fields: Sequence[str]) -> tuple[str, ...]:
    """For ``postProcessing/<function>/<instance>/<field>``, the files
    :func:`probes_function_with_fields` writes for ``fields``, under the same
    instance."""
    parts = PurePosixPath(probe_path).parts
    if len(parts) != 4 or parts[0] != "postProcessing":
        raise ValueError(f"{probe_path!r} is not a probes file, postProcessing/<function>/<instance>/<field>")
    function = probes_function_with_fields(parts[1], fields)
    return tuple(f"postProcessing/{function}/{parts[2]}/{field}" for field in fields)
