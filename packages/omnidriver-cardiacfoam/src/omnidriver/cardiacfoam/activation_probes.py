"""cardiacFOAM activation times from an OpenFOAM ``probes`` file of ``activationTime``.

Each fact below comes from a real run or from source, logged in
docs/solver-learning/cardiacfoam.md, section Q:

- the values are seconds: ``activationTime``'s own field file declares
  ``dimensions [0 0 1 0 0 0 0]`` (Q2), and ``myocardiumDomain`` builds it
  with ``dimTime``;
- ``-1`` means never activated: the field starts at ``dimensionedScalar(
  "unactivated", dimTime, -1.0)`` (``myocardiumDomain.C``), and a real run
  writes ``-1`` for every probe not yet reached (Q1). Core resolves it before
  any unit conversion (``core.quantities.read_quantities``);
- the value is the **last** row: the declared file is the ``samplePoints``
  step's ``postProcess -latestTime`` output, one row at the final time (N2),
  and the solve's own per-write-time rows before it are cumulative;
- ``probes`` with no ``interpolationScheme`` samples the cell containing
  each configured location (``interpolationCell``), so the ``# Probe``
  header is the agent's own input echoed back, never where the value came
  from.

Sampling rule ``cell-containing``. ``sampled_at`` is that cell's centre, in
metres, in cardiacFOAM's own frame: read from the same function run on
``writeCellCentres``' components (``openfoam.probes.CELL_CENTRE_FIELDS``),
which the record's ``writeCellCentres`` and ``samplePointCentres`` steps
write. Q3/Q4 found those values equal to the centre of the very cell
``probes`` reports under ``-debug-switch probes=1``, on the hex mesh and
on the tet mesh alike. The header locations of both files must agree, and
so must their last rows' times; otherwise the centres describe some other
sampling and are refused. Names are probe indices, ``"0"``...``"8"``.
Nothing here orients or pairs: that is the agent's step.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.quantities import RawSample, ReadRequest
from omnidriver.openfoam.probes import CELL_CENTRE_FIELDS, ProbeSeries, parse_probe_series, sibling_probe_files

ACTIVATION_PROBES_FORMAT = "cardiacfoam_activation_probes"


def _series(case_root: Path, relpath: str, *, written_by: str) -> ProbeSeries:
    path = case_root / relpath
    try:
        text = path.read_text()
    except OSError as exc:
        raise ValueError(f"cannot read {relpath} under {case_root}, which {written_by} writes: {exc}") from exc
    return parse_probe_series(text, source=relpath)


class ActivationProbeReader:
    value_unit = "s"
    sentinels = frozenset({-1.0})
    sampling_rule = "cell-containing"
    coordinate_unit = "m"
    takes_points = False

    def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
        case_root = Path(case_root)
        values = _series(case_root, artifact.path_pattern, written_by="the probes function")
        by_name = {str(index): column for column, (index, _) in enumerate(values.locations)}
        unknown = [name for name in request.names if name not in by_name]
        if unknown:
            raise ValueError(f"{unknown[0]!r} is not a probe of {artifact.path_pattern}; it has probes {sorted(by_name, key=int)}")
        centres = []
        for relpath in sibling_probe_files(artifact.path_pattern, CELL_CENTRE_FIELDS):
            series = _series(case_root, relpath, written_by="postProcess -func writeCellCentres, then this probes function on its components,")
            for (index, at), (_, expected) in zip(series.locations, values.locations):
                if at != expected:
                    raise ValueError(f"{relpath}: probe {index} is at {list(at)}, not where {artifact.path_pattern} probed, {list(expected)}")
            if len(series.locations) != len(values.locations):
                raise ValueError(f"{relpath} has {len(series.locations)} probes; {artifact.path_pattern} has {len(values.locations)}")
            if series.times[-1] != values.times[-1]:
                raise ValueError(f"{relpath} ends at time {series.times[-1]}, {artifact.path_pattern} at {values.times[-1]}")
            centres.append(series.rows[-1])
        samples = []
        for name in request.names:
            column = by_name[name]
            if int(name) in values.not_found:
                raise ValueError(f"probe {name!r} of {artifact.path_pattern} is '# Not Found': no cell contains {list(values.locations[column][1])}")
            samples.append(RawSample(name=name, value=values.rows[-1][column],
                                     sampled_at=tuple(axis[column] for axis in centres)))
        return tuple(samples)
