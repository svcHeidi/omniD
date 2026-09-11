"""OpenFOAM restart-time selection for adapter-owned provenance."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def selected_start_time(
    case_root: Path,
    *,
    control_dict_relpath: str,
    read_value: Callable[[Path, str], str | None],
) -> str:
    """Resolve OpenFOAM ``startFrom``/``startTime`` to one time directory."""
    default = "0"
    control_dict = case_root / control_dict_relpath
    if not control_dict.is_file():
        return default

    start_from = (read_value(control_dict, "startFrom") or "startTime").strip()
    if start_from not in {"latestTime", "firstTime"}:
        value = read_value(control_dict, "startTime")
        return value.strip() if value is not None else default

    candidates: list[str] = []
    try:
        children = case_root.iterdir()
    except OSError:
        return default
    for child in children:
        if not child.is_dir():
            continue
        try:
            float(child.name)
        except ValueError:
            continue
        candidates.append(child.name)
    if not candidates:
        return default
    selector = max if start_from == "latestTime" else min
    return selector(candidates, key=float)
