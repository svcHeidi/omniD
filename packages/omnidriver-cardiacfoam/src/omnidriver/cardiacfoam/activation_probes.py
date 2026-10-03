"""cardiacFOAM activation times, in seconds, from an OpenFOAM ``probes`` file of ``activationTime``."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.quantities import RawSample, ReadRequest
from omnidriver.openfoam.probes import ProbeSeries, interpolation_scheme, parse_probe_series

ACTIVATION_PROBES_FORMAT = "cardiacfoam_activation_probes"
# A cellPoint probe's location is the point itself; OpenFOAM's default ``cell``
# scheme gives the containing cell's centre, which this reader does not report.
# The scheme is read from the case's own system/<function> dict, never defaulted.
_REQUIRED_SCHEME = "cellPoint"


def _series(case_root: Path, relpath: str) -> ProbeSeries:
    path = case_root / relpath
    try:
        text = path.read_text()
    except OSError as exc:
        raise ValueError(f"cannot read {relpath} under {case_root}, which the probes function writes: {exc}") from exc
    return parse_probe_series(text, source=relpath)


class ActivationProbeReader:
    value_unit = "s"
    # myocardiumDomain initialises the field to -1 (never activated); core
    # resolves a sentinel before any unit conversion.
    sentinels = frozenset({-1.0})
    sampling_rule = "point"
    coordinate_unit = "m"
    takes_points = False

    def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
        case_root = Path(case_root)
        scheme = interpolation_scheme(case_root, artifact.path_pattern)
        if scheme != _REQUIRED_SCHEME:
            raise ValueError(
                f"{artifact.path_pattern}'s probes function samples with interpolationScheme {scheme!r}; "
                f"only {_REQUIRED_SCHEME!r} is supported. A {scheme!r} probe's location is the containing "
                "cell's centre, which this reader does not report without a record providing cell centres"
            )
        values = _series(case_root, artifact.path_pattern)
        by_name = {str(index): column for column, (index, _) in enumerate(values.locations)}
        unknown = [name for name in request.names if name not in by_name]
        if unknown:
            raise ValueError(f"{unknown[0]!r} is not a probe of {artifact.path_pattern}; it has probes {sorted(by_name, key=int)}")
        samples = []
        # The declared file is the samplePoints step's `postProcess -latestTime`
        # output: one row, at the final time. The solve's own rows are cumulative.
        for name in request.names:
            column = by_name[name]
            if int(name) in values.not_found:
                raise ValueError(f"probe {name!r} of {artifact.path_pattern} is '# Not Found': no cell contains {list(values.locations[column][1])}")
            samples.append(RawSample(name=name, value=values.rows[-1][column], sampled_at=values.locations[column][1]))
        return tuple(samples)
