"""The frozen tolerance protocol for E1."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


_RATIONALE = (
    "Transcribed verbatim from the committed regression reference, which "
    "predates E1; adopting it involves no post hoc threshold selection."
)


@dataclass(frozen=True)
class _ReferencePoint:
    data_file: str
    time: float
    variable: str
    expected: float
    tolerance: float


def _parse_columnar_reference(text: str) -> list[_ReferencePoint]:
    """Parse a `file time variable expected tolerance` reference file."""
    points: list[_ReferencePoint] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split()
        if len(cols) < 5:
            return []
        data_file, time, variable, expected, tolerance = cols[:5]
        try:
            points.append(
                _ReferencePoint(
                    data_file, float(time), variable,
                    float(expected), float(tolerance),
                )
            )
        except ValueError:
            # Non-numeric where numbers are expected -> not this layout.
            return []
    return points


@dataclass(frozen=True)
class MetricToleranceRow:
    """A `kind key metric expected tolerance` row (norms, summaries, topology)."""

    case_dir: str
    kind: str
    key: str
    metric: str
    expected: float
    tolerance: float
    source_reference: str
    rationale: str


@dataclass(frozen=True)
class Protocol:
    rows: tuple["ToleranceRow", ...]
    metric_rows: tuple[MetricToleranceRow, ...]


@dataclass(frozen=True)
class ToleranceRow:
    case_dir: str
    data_file: str
    variable: str
    time: float
    expected: float
    tolerance: float
    source_reference: str
    rationale: str


def transcribe_reference(
    case_dir: str, reference_relpath: str, reference_text: str
) -> list[ToleranceRow]:
    """Turn one committed columnar reference into frozen tolerance rows."""
    return [
        ToleranceRow(
            case_dir=case_dir,
            data_file=point.data_file,
            variable=point.variable,
            time=point.time,
            expected=point.expected,
            tolerance=point.tolerance,
            source_reference=reference_relpath,
            rationale=_RATIONALE,
        )
        for point in _parse_columnar_reference(reference_text)
    ]


def _metric_records(reference_text: str) -> list[tuple[str, str, str, float, float]]:
    """Parse the `kind key metric expected tolerance` layout."""
    records: list[tuple[str, str, str, float, float]] = []
    for raw in reference_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split()
        if len(cols) < 5:
            return []
        kind, key, metric, expected, tolerance = cols[:5]
        try:
            float(key)
        except ValueError:
            pass
        else:
            # Second column is numeric -> this is the columnar time layout.
            return []
        try:
            records.append((kind, key, metric, float(expected), float(tolerance)))
        except ValueError:
            return []
    return records


def transcribe_metric_reference(
    case_dir: str, reference_relpath: str, reference_text: str
) -> list[MetricToleranceRow]:
    """Turn one committed metric reference into frozen tolerance rows."""
    return [
        MetricToleranceRow(
            case_dir=case_dir,
            kind=kind,
            key=key,
            metric=metric,
            expected=expected,
            tolerance=tolerance,
            source_reference=reference_relpath,
            rationale=_RATIONALE,
        )
        for kind, key, metric, expected, tolerance in _metric_records(reference_text)
    ]


def write_protocol(
    rows: list[ToleranceRow],
    path: Path,
    *,
    metric_rows: list[MetricToleranceRow] | None = None,
) -> None:
    """Write the frozen protocol. Sorted, so regeneration produces no diff noise."""
    payload = {
        "schema_version": 1,
        "description": (
            "Frozen numerical tolerances for E1. Do not edit a tolerance after "
            "seeing a comparison result; add a new row with its own rationale."
        ),
        "rows": [
            asdict(row)
            for row in sorted(
                rows, key=lambda r: (r.case_dir, r.data_file, r.variable, r.time)
            )
        ],
        "metric_rows": [
            asdict(row)
            for row in sorted(
                metric_rows or [],
                key=lambda r: (r.case_dir, r.kind, r.key, r.metric),
            )
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def load_protocol(path: Path) -> Protocol:
    payload = yaml.safe_load(path.read_text())
    return Protocol(
        rows=tuple(ToleranceRow(**row) for row in payload.get("rows", ())),
        metric_rows=tuple(
            MetricToleranceRow(**row) for row in payload.get("metric_rows", ())
        ),
    )
