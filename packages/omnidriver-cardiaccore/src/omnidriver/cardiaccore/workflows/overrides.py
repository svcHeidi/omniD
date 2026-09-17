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


# NOTE on why this map did not grow when catalogs/inputs.py grew from 10 to
# 87 declared entries: a DictEntry becomes an overridable x value only once
# it also has a row here (a declaration with no target is unreachable, by
# design -- see the inputs.py module docstring). The 77 new entries
# (setCardiacScarDict, setPurkinjeScarDict, generatePurkinjeTreeDict's
# per-ventricle block and its two top-level keys, and the
# setCardiacConductivity bidomain pair) are deliberately left without a row:
#
# - setCardiacScarDict / setPurkinjeScarDict do not exist in the selected
#   bivCase at all (only in cardiacCoreStandalone/tutorials/template), and no
#   workflow here schedules either utility. `read_input_values(paths=None)`
#   (used whenever a workflow's spec carries no `active_input_paths`, e.g.
#   the human-purkinje-slab tutorial) would read every row in this map by
#   default; `read_foam_entry` tolerates a missing file (returns None), so
#   this would not crash, but a target that nothing ever schedules is pure
#   surface area for no benefit.
# - generatePurkinjeTreeDict's `<ventKey>.*` entries are `dynamic_path=True`:
#   there is no single fixed `key` string a placeholder segment could route
#   to, and this dict is exactly the one `workflows/preprocessing.py` freezes
#   via `PURKINJE_TREE_INPUT_PATHS` -- adding a route here is one of the two
#   steps ("adding it to `_TARGETS` and to a workflow's `active_input_paths`")
#   that make a declared key mutable, and the tree parameters must stay
#   declared-only. `hisBundleSeed`/`growthModel` are left out too, for the
#   same reason: PURKINJE_TREE_INPUT_PATHS already excludes the whole
#   document, not just the per-ventricle block.
# - the conductivityIntracellular/conductivityExtracellular bidomain pair is a
#   genuine co-requirement (both present or neither -- see the CONDUCTIVITY_
#   ENTRIES comment in inputs.py) that the validator cannot check with the
#   structured predicate vocabulary; adding a route without a way to enforce
#   the pairing would let a caller silently write one half of the pair only,
#   which setCardiacConductivity.C then rejects at run time with a
#   FatalIOError instead of at override-validation time.
#
# This mirrors catalogs/utilities.py: 11 native utilities are declared there,
# and only 5 are scheduled by a workflow. Declaring is not scheduling, and
# here declaring is not targeting.
_TARGETS: dict[str, InputTarget] = {
    "$CARDIAC_CONDUCTIVITY.df": InputTarget("system/setCardiacConductivityDict", "df"),
    "$CARDIAC_CONDUCTIVITY.ds": InputTarget("system/setCardiacConductivityDict", "ds"),
    "$CARDIAC_CONDUCTIVITY.dn": InputTarget("system/setCardiacConductivityDict", "dn"),
    "$CARDIAC_CONDUCTIVITY.fiberField": InputTarget("system/setCardiacConductivityDict", "fiberField"),
    "$CARDIAC_CONDUCTIVITY.sheetField": InputTarget("system/setCardiacConductivityDict", "sheetField"),
    "$CARDIAC_ANATOMY.zApicalMid": InputTarget("system/setCardiacAnatomyDict", "zApicalMid"),
    "$CARDIAC_ANATOMY.zMidBasal": InputTarget("system/setCardiacAnatomyDict", "zMidBasal"),
    "$CARDIAC_ANATOMY.zApexCap": InputTarget("system/setCardiacAnatomyDict", "zApexCap"),
    "$PURKINJE_SLAB.thickness": InputTarget("system/setPurkinjeSlabDict", "thickness"),
    "$PURKINJE_SLAB.multiplier": InputTarget("system/setPurkinjeSlabDict", "multiplier"),
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
    return validated


def apply_input_overrides(case_root: Path, overrides: Mapping[str, Any] | None) -> None:
    for driver_path, value in validate_input_overrides(overrides).items():
        target = _TARGETS[driver_path]
        update_foam_entry(case_root / target.file_relpath, target.key, value)


def read_input_values(case_root: Path, *, paths: tuple[str, ...] | None = None) -> dict[str, Any]:
    from omnidriver.openfoam.mutators import read_foam_entry
    selected_paths = tuple(_TARGETS) if paths is None else paths
    return {driver_path: read_foam_entry(case_root / _TARGETS[driver_path].file_relpath, _TARGETS[driver_path].key) for driver_path in selected_paths}
