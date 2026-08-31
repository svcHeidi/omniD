"""The frozen tolerance protocol for E1.

EXPERIMENTAL_EVIDENCE_TABLE.md requires that thresholds "must not be selected
after seeing the final comparison". Most rows need no pilot: the committed
``.reference`` files already carry per-point tolerances authored long before E1
existed, so adopting them is preregistration-safe by construction. Each row
records where its tolerance came from, so that is auditable rather than
asserted.

Two committed reference layouts exist and both carry tolerances:

- columnar, ``file time variable expected tolerance`` -- time-series probe
  points (singleCell, Niederer, electromechanical, rotorInstability);
- metric, ``kind key metric expected tolerance`` -- the manufactured-solution
  and purkinje cases, carrying the solver-emitted L1/L2/Linf norm tolerances
  alongside summary and topology checks.

Both predate E1, so both are preregistration-safe to adopt. No pilot study is
required for the norm rows: their tolerances are already committed.
"""
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
    """Parse a `file time variable expected tolerance` reference file.

    Returns [] for reference files that don't follow this columnar layout
    (e.g. the bidomain `kind key metric ...` metric style), signalling the
    caller to fall back to the case's own regressionTest.sh as the gate.

    Duplicated (not imported) from
    ``regression_equivalence.dual_run.parse_columnar_reference`` in
    cardiacfoam's test tree: that module imports
    ``regression_equivalence.registry``, a sibling module that lives only in
    cardiacfoam's own tests directory, so importing it from core's test suite
    would pull a cardiacfoam-only test package into a core-only install (the
    regression this duplication fixes, see
    docs/superpowers/plans/2026-08-27-core-completion-phase-2.md, Task 1).
    This function itself is generic -- no cardiac knowledge -- so copying it
    is safe and cheaper than relocating this whole module.
    """
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
    """Turn one committed columnar reference into frozen tolerance rows.

    Returns [] for references that are not in the columnar
    `file time variable expected tolerance` layout (e.g. the bidomain
    `kind key metric ...` style), which carry no per-point tolerance to adopt.
    """
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
    """Parse the `kind key metric expected tolerance` layout.

    Returns [] for the columnar layout, which is distinguished by its second
    column parsing as a float (a time), where this layout's second column is a
    field or quantity name.
    """
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
