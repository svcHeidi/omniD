"""Explicit conversion from raw CObiveco coordinates to cardiacCore fields."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
from omnidriver.openfoam.mutators import read_foam_entry


from ..catalogs.support_boundary import CARDIACCORE_COBIVECO_TARGET


def read_cobiveco_target_convention(case_root: Path) -> dict[str, float]:
    """Read the selected case convention without evaluating its dictionary.

    The transmural bounds are named by anatomy, not by numeric order:
    ``coordinatesConvention.H`` reads ``endocardium``/``epicardium`` precisely
    because the two coordinate systems order them oppositely (UVC 0=endo,
    1=epi; CObiveco 1=endo, 0=epi), so ``min``/``max`` cannot say which end
    is which.
    """
    dictionary = case_root / "system" / "coordinatesConventionDict"
    locations = {
        "transmural_endocardium": ("endocardium", "transmural"),
        "transmural_epicardium": ("epicardium", "transmural"),
        "lv_value": ("LV", "intraventricularChambers"),
        "rv_value": ("RV", "intraventricularChambers"),
    }
    result = {}
    for name, (key, scope) in locations.items():
        value = read_foam_entry(dictionary, key, scope=scope)
        if value is None:
            raise ValueError(f"{dictionary}: missing {scope}.{key}")
        try:
            result[name] = float(value)
        except ValueError as exc:
            raise ValueError(f"{dictionary}: {scope}.{key} must be a scalar") from exc
    return result


def validate_cobiveco_target_convention(target: Mapping[str, float]) -> None:
    """Reject use against a case that expects a different UVC convention."""
    missing = set(CARDIACCORE_COBIVECO_TARGET).difference(target)
    if missing:
        raise ValueError(f"target convention is missing: {', '.join(sorted(missing))}")
    mismatches = {
        key: (target[key], expected)
        for key, expected in CARDIACCORE_COBIVECO_TARGET.items()
        if target[key] != expected
    }
    if mismatches:
        raise ValueError(
            "raw CObiveco conversion requires target convention "
            f"{CARDIACCORE_COBIVECO_TARGET}; got mismatches {mismatches}"
        )


def normalize_cobiveco_coordinates(
    tv: np.ndarray, tm: np.ndarray, ab: np.ndarray, *, target_convention: Mapping[str, float],
) -> dict[str, np.ndarray]:
    """Map raw CObiveco fields to the current cardiacCore UVC convention.

    Raw CObiveco uses ``tv: 0=LV, 1=RV`` and ``tm: 0=epi, 1=endo``. The
    cardiacCore convention used by its checked-in cases is ``LV=-1, RV=1``
    and ``transmural endocardium=0, epicardium=1``. The caller must first supply the
    target case's parsed convention; this rejects a silent mismatch.
    """
    validate_cobiveco_target_convention(target_convention)
    tv, tm, ab = (np.asarray(values, dtype=float) for values in (tv, tm, ab))
    if any(values.ndim != 1 for values in (tv, tm, ab)):
        raise ValueError("CObiveco tv, tm, and ab must be one-dimensional arrays")
    if not (len(tv) == len(tm) == len(ab)):
        raise ValueError("CObiveco tv, tm, and ab arrays must have equal lengths")
    if not all(np.all(np.isfinite(values)) for values in (tv, tm, ab)):
        raise ValueError("raw CObiveco arrays must contain only finite values")
    if np.any((tv < 0) | (tv > 1)) or np.any((tm < 0) | (tm > 1)):
        raise ValueError("raw CObiveco tv and tm values must lie in [0, 1]")
    return {
        "uvc_transmural": 1.0 - tm,
        "uvc_intraventricular": 2.0 * tv - 1.0,
        "uvc_longitudinal": ab.copy(),
    }
