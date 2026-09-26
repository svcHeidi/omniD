"""A value read from a result, with everything needed to judge it.

Design: docs/superpowers/specs/2026-09-26-results-as-quantities-design.md §3.
Nothing here names a solver or a physical quantity. A reader declares the
unit of what it returns, its sentinels (raw values meaning "never reached"),
its sampling rule and the unit of its coordinates. Core resolves sentinels
first and converts after (``reading.read_quantities``, ``reading.converted``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, Protocol

from .units import dimension_of

if TYPE_CHECKING:
    from ..runtime.models import DataArtifact

Point = tuple[float, float, float]
QUANTITY_STATUSES = frozenset({"evaluated", "not_reached", "not_evaluated"})


@dataclass(frozen=True)
class Quantity:
    """One named value from one artifact.

    ``status``: ``evaluated`` (``value`` is a finite number in ``unit``),
    ``not_reached`` (the reader's sentinel: the solver says it never
    happened) or ``not_evaluated`` (nothing was read; ``reason`` says why).
    ``sampled_at`` is where the solver says it sampled, in
    ``sampled_at_unit``, in the solver's own frame. ``sampling_rule`` is the
    reader's declared rule, e.g. the nearest mesh point or the containing
    cell: plugin vocabulary, carried and never interpreted.
    ``sampled_at_unit`` and ``reason`` go beyond the spec's field list
    (2026-09-26): a coordinate triple without a unit is ambiguous, and a
    ``not_evaluated`` without a reason cannot be acted on.
    """

    name: str
    value: float | None
    unit: str | None
    status: str
    source_artifact: str
    sampled_at: Point | None
    sampled_at_unit: str | None
    sampling_rule: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        label = f"quantity {self.name!r}"
        if self.status not in QUANTITY_STATUSES:
            raise ValueError(f"{label}: status {self.status!r} is not one of {sorted(QUANTITY_STATUSES)}")
        if (self.value is not None) != (self.status == "evaluated"):
            raise ValueError(
                f"{label}: a value is present exactly when the status is 'evaluated' "
                f"(status {self.status!r}, value {self.value!r})"
            )
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError(f"{label}: value {self.value!r} is not finite")
        if self.status == "not_evaluated":
            if not self.reason:
                raise ValueError(f"{label} is not_evaluated without a reason")
        elif self.unit is None or not self.sampling_rule:
            raise ValueError(f"{label}: a read quantity carries its unit and sampling rule")
        if self.unit is not None:
            dimension_of(self.unit)
        if (self.sampled_at is None) != (self.sampled_at_unit is None):
            raise ValueError(f"{label}: sampled_at and sampled_at_unit are given together or not at all")
        if self.sampled_at_unit is not None and dimension_of(self.sampled_at_unit) != "length":
            raise ValueError(f"{label}: sampled_at_unit {self.sampled_at_unit!r} is not a length")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "value": self.value, "unit": self.unit, "status": self.status,
            "source_artifact": self.source_artifact,
            "sampled_at": list(self.sampled_at) if self.sampled_at is not None else None,
            "sampled_at_unit": self.sampled_at_unit, "sampling_rule": self.sampling_rule,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RawSample:
    """What a reader returns: a raw number, before sentinels or units."""

    name: str
    value: float
    sampled_at: Point | None = None


@dataclass(frozen=True)
class ReadRequest:
    """The names to read and, for a reader that samples at supplied points,
    where: each point is in the reader's ``coordinate_unit`` (core converted
    it from the request's unit). Empty for a reader that samples where the
    solver chose."""

    names: tuple[str, ...]
    points: Mapping[str, Point] = field(default_factory=lambda: MappingProxyType({}))


class ArtifactValueReader(Protocol):
    """What ``get_artifact_value_reader(format)`` returns.

    ``read`` refuses by raising ``ValueError`` naming why. It returns one
    ``RawSample`` per requested name, in any order; core checks the names.
    """

    value_unit: str
    sentinels: frozenset[float]
    sampling_rule: str
    coordinate_unit: str | None
    takes_points: bool

    def read(self, case_root: Path, artifact: "DataArtifact", request: ReadRequest) -> tuple[RawSample, ...]: ...


def not_evaluated(names: tuple[str, ...], *, source_artifact: str, reason: str) -> tuple[Quantity, ...]:
    return tuple(
        Quantity(name=name, value=None, unit=None, status="not_evaluated", source_artifact=source_artifact,
                 sampled_at=None, sampled_at_unit=None, sampling_rule=None, reason=reason)
        for name in names
    )
