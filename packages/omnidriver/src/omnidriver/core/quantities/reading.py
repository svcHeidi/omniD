"""Reading quantities through a plugin's reader: sentinels first, then units."""
from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from .errors import QuantityReadError, ReaderDeclarationError, UnitError
from .model import Quantity, ReadRequest
from .units import check_convertible, convert, dimension_of

_DECLARED = ("value_unit", "sentinels", "sampling_rule", "coordinate_unit", "takes_points")


def check_reader(reader: Any, *, artifact_format: str) -> None:
    """Refuse, by name, a reader whose declaration core cannot use."""
    label = f"the reader for format {artifact_format!r}"
    missing = [name for name in _DECLARED if not hasattr(reader, name)]
    if missing or not callable(getattr(reader, "read", None)):
        raise ReaderDeclarationError(f"{label} does not declare {missing or ['read']}")
    try:
        dimension_of(reader.value_unit)
        if reader.coordinate_unit is not None and dimension_of(reader.coordinate_unit) != "length":
            raise ReaderDeclarationError(f"{label}: coordinate_unit {reader.coordinate_unit!r} is not a length")
    except UnitError as exc:
        raise ReaderDeclarationError(f"{label}: {exc}") from exc
    if not isinstance(reader.sampling_rule, str) or not reader.sampling_rule:
        raise ReaderDeclarationError(f"{label} declares no sampling rule")
    if reader.takes_points and reader.coordinate_unit is None:
        raise ReaderDeclarationError(f"{label} takes points but declares no coordinate_unit to take them in")
    if any(not isinstance(s, (int, float)) or not math.isfinite(s) for s in reader.sentinels):
        raise ReaderDeclarationError(f"{label}: every sentinel must be a finite number, got {sorted(map(repr, reader.sentinels))}")


def read_quantities(reader: Any, case_root: Path, artifact: Any, request: ReadRequest) -> tuple[Quantity, ...]:
    """Read ``request.names`` from one artifact, in request order.

    A sentinel is a statement ("never reached"), not a number, so it becomes
    ``not_reached`` here, before anything could convert it: ``-1 s`` is never
    ``-1000 ms`` (spec §2)."""
    check_reader(reader, artifact_format=artifact.format)
    if reader.takes_points:
        missing = [name for name in request.names if name not in request.points]
        if missing:
            raise QuantityReadError(f"the {artifact.format!r} reader samples at supplied points; none given for {missing}")
    elif request.points:
        raise QuantityReadError(
            f"the {artifact.format!r} reader samples where the solver chose, so it takes no points; "
            f"got points for {sorted(request.points)}"
        )
    by_name: dict[str, Any] = {}
    for sample in reader.read(Path(case_root), artifact, request):
        if sample.name in by_name:
            raise QuantityReadError(f"the {artifact.format!r} reader returned {sample.name!r} twice")
        by_name[sample.name] = sample
    absent = [name for name in request.names if name not in by_name]
    extra = sorted(set(by_name) - set(request.names))
    if absent or extra:
        raise QuantityReadError(
            f"the {artifact.format!r} reader did not answer the request: missing {absent}, unrequested {extra}"
        )
    quantities = []
    for name in request.names:
        sample = by_name[name]
        if sample.value in reader.sentinels:
            status, value = "not_reached", None
        elif not math.isfinite(sample.value):
            raise QuantityReadError(f"{name!r} in {artifact.path_pattern}: value {sample.value!r} is not finite")
        else:
            status, value = "evaluated", float(sample.value)
        sampled_at = tuple(float(c) for c in sample.sampled_at) if sample.sampled_at is not None else None
        if reader.takes_points and sampled_at is None:
            # I1, controller review 2026-09-26: a pre-registered
            # max_sampling_offset checks a sample's location, so a reader
            # that samples at supplied points must report where -- silently
            # accepting "no location" would let that stated guard pass
            # unchecked (`comparison._metric` only compares an offset it has).
            raise QuantityReadError(
                f"the {artifact.format!r} reader samples at supplied points, but reported no sampled_at for "
                f"{name!r}; a stated max_sampling_offset could not be checked against an unknown location"
            )
        quantities.append(Quantity(
            name=name, value=value, unit=reader.value_unit, status=status,
            source_artifact=artifact.path_pattern, sampled_at=sampled_at,
            sampled_at_unit=reader.coordinate_unit if sampled_at is not None else None,
            sampling_rule=reader.sampling_rule,
        ))
    return tuple(quantities)


def converted(quantity: Quantity, to_unit: str) -> Quantity:
    """The same quantity in ``to_unit``. A quantity with no value keeps none,
    but its unit must still convert: a mismatch is refused either way."""
    if quantity.unit is None:
        return quantity
    check_convertible(quantity.unit, to_unit)
    value = None if quantity.value is None else convert(quantity.value, quantity.unit, to_unit)
    return replace(quantity, value=value, unit=to_unit)
