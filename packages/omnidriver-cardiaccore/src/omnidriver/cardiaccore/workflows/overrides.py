"""Validated user-requested changes for supported cardiacCore inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

from omnidriver.openfoam.mutators import update_foam_entry

from ..catalogs.inputs import CATALOG


@dataclass(frozen=True)
class InputTarget:
    """One reviewed x value and its native dictionary location."""

    file_relpath: str
    key: str


_TARGETS: dict[str, InputTarget] = {
    "$CARDIAC_CONDUCTIVITY.df": InputTarget("system/setCardiacConductivityDict", "df"),
    "$CARDIAC_CONDUCTIVITY.ds": InputTarget("system/setCardiacConductivityDict", "ds"),
    "$CARDIAC_CONDUCTIVITY.dn": InputTarget("system/setCardiacConductivityDict", "dn"),
    "$CARDIAC_CONDUCTIVITY.fiberField": InputTarget("system/setCardiacConductivityDict", "fiberField"),
    "$CARDIAC_CONDUCTIVITY.sheetField": InputTarget("system/setCardiacConductivityDict", "sheetField"),
    "$CARDIAC_ANATOMY.zApicalMid": InputTarget("system/setCardiacAnatomyDict", "zApicalMid"),
    "$CARDIAC_ANATOMY.zMidBasal": InputTarget("system/setCardiacAnatomyDict", "zMidBasal"),
    "$CARDIAC_ANATOMY.zApexCap": InputTarget("system/setCardiacAnatomyDict", "zApexCap"),
    "$CARDIAC_ANATOMY.grooveMode": InputTarget("system/setCardiacAnatomyDict", "grooveMode"),
    "$PURKINJE_SLAB.thickness": InputTarget("system/setPurkinjeSlabDict", "thickness"),
    "$PURKINJE_SLAB.multiplier": InputTarget("system/setPurkinjeSlabDict", "multiplier"),
    "$PURKINJE_MORPHOMETRY.grooveMode": InputTarget("system/setPurkinjeMorphometryDict", "grooveMode"),
}

_ENTRIES = {entry.driver_path: entry for entry in CATALOG.entries}


def validate_input_overrides(overrides: Mapping[str, Any] | None, *, allowed_paths: tuple[str, ...] | None = None) -> dict[str, Any]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise TypeError("input_overrides must be a JSON object mapping reviewed paths to values")
    validated: dict[str, Any] = {}
    for driver_path, value in overrides.items():
        if not isinstance(driver_path, str) or driver_path not in _TARGETS:
            known = ", ".join(sorted(_TARGETS))
            raise ValueError(
                f"input override {driver_path!r} is not supported by the selected bivCase workflow. "
                f"Known paths: {known}"
            )
        if allowed_paths is not None and driver_path not in allowed_paths:
            known = ", ".join(allowed_paths)
            raise ValueError(
                f"input override {driver_path!r} is not supported by this selected workflow. "
                f"Allowed paths: {known}"
            )
        entry = _ENTRIES[driver_path]
        if entry.value_kind == "scalar":
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"input override {driver_path!r} must be a JSON number")
        elif entry.value_kind in {"word", "enum"}:
            if not isinstance(value, str) or not value:
                raise TypeError(f"input override {driver_path!r} must be a non-empty JSON string")
        else:
            raise ValueError(f"input override {driver_path!r} has unsupported value kind {entry.value_kind!r}")
        if entry.enum_values and value not in entry.enum_values:
            raise ValueError(f"input override {driver_path!r} value {value!r} not in enum {entry.enum_values}")
        validated[driver_path] = value
    _validate_supported_combinations(validated)
    return validated


def _validate_supported_combinations(overrides: Mapping[str, Any]) -> None:
    manual_paths = ("$CARDIAC_ANATOMY.grooveMode", "$PURKINJE_MORPHOMETRY.grooveMode")
    if any(overrides.get(path) == "manual" for path in manual_paths):
        raise ValueError(
            "grooveMode='manual' requires the conditional anteriorGroove and posteriorGroove inputs. "
            "Those inputs are documented but not yet part of this selected auto-mode bivCase workflow."
        )


def apply_input_overrides(case_root: Path, overrides: Mapping[str, Any] | None) -> None:
    for driver_path, value in validate_input_overrides(overrides).items():
        target = _TARGETS[driver_path]
        update_foam_entry(case_root / target.file_relpath, target.key, value)


def read_input_values(case_root: Path, *, paths: tuple[str, ...] | None = None) -> dict[str, Any]:
    from omnidriver.openfoam.mutators import read_foam_entry
    selected_paths = tuple(_TARGETS) if paths is None else paths
    return {driver_path: read_foam_entry(case_root / _TARGETS[driver_path].file_relpath, _TARGETS[driver_path].key) for driver_path in selected_paths}
