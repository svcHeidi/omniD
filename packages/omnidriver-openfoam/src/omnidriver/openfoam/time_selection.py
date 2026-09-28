"""OpenFOAM restart-time selection for adapter-owned provenance."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from omnidriver.core.tutorial_records import TutorialRecordError


class TimeSelectionError(TutorialRecordError):
    """``startFrom``/``startTime`` cannot be resolved to a single time
    directory -- a ``FatalIOError`` in OpenFOAM's own
    ``Foam::Time::setControls`` (``src/OpenFOAM/db/Time/Time.C``), refused
    here by name.

    Subclasses :class:`TutorialRecordError` so it reaches the CLI's generic
    exception handling whether raised during planning or, via
    ``get_input_roots``, during a run's checkpoint/resume validation.
    """


def selected_start_time(
    case_root: Path,
    *,
    control_dict_relpath: str,
    read_value: Callable[[Path, str], str | None],
    instance_directory_pattern: str,
) -> str | None:
    """Resolve OpenFOAM's ``startFrom``/``startTime`` to one time directory,
    exactly as ``Foam::Time::setControls`` does (OpenFOAM v2412,
    ``src/OpenFOAM/db/Time/Time.C``).

    Returns ``None`` when ``control_dict_relpath`` names no file: a case with
    no ``controlDict`` may not be OpenFOAM-shaped at all (e.g. cardiacCore's
    ``Allrun``-only cases, which always write to ``0/`` and have no time
    concept of their own), so this answers "contribute nothing" rather than
    inventing ``"0"``.

    ``startFrom`` absent defaults to ``"latestTime"`` (mirrors
    ``setControls``'s own ``getOrDefault<word>("startFrom", "latestTime")``).
    ``startFrom startTime`` with no ``startTime`` entry, or any other
    unrecognised ``startFrom``, raises :class:`TimeSelectionError` -- both are
    a ``FatalIOError`` in real OpenFOAM, never silently answered.

    With no time directories present, ``firstTime``/``latestTime`` still
    answers ``"0"`` -- not a fallback, but ``Time``'s own constructor default
    (``startTime_(0)``), left untouched when ``setControls``'s ``if
    (nTimes)`` guard never fires.

    ``instance_directory_pattern`` is the stack's merged
    ``CaseRuntimeConventions.instance_directory_pattern`` -- the same regex
    staging, discovery and snapshots use to recognise a time directory, never
    a bare ``float(name)`` check (which would disagree with the regex on
    names like ``inf``, ``nan``, ``1_0`` or ``1E-05``).
    """
    control_dict = case_root / control_dict_relpath
    if not control_dict.is_file():
        return None

    start_from = (read_value(control_dict, "startFrom") or "latestTime").strip()
    if start_from == "startTime":
        value = read_value(control_dict, "startTime")
        if value is None:
            raise TimeSelectionError(
                f"{control_dict}: startFrom is 'startTime' but no startTime "
                "entry is set -- OpenFOAM's Foam::Time::setControls reads it "
                'with controlDict_.readEntry("startTime", startTime_), a '
                "FatalIOError when the key is absent"
            )
        return value.strip()

    if start_from not in {"firstTime", "latestTime"}:
        raise TimeSelectionError(
            f"{control_dict}: startFrom must be 'startTime', 'firstTime' or "
            f"'latestTime', found {start_from!r} -- OpenFOAM's "
            'Foam::Time::setControls: "expected startTime, firstTime or '
            'latestTime"'
        )

    pattern = re.compile(instance_directory_pattern)
    candidates: list[str] = []
    try:
        children = case_root.iterdir()
    except OSError:
        children = ()
    for child in children:
        if not child.is_dir():
            continue
        if not pattern.fullmatch(child.name):
            continue
        candidates.append(child.name)
    if not candidates:
        return "0"
    selector = max if start_from == "latestTime" else min
    return selector(candidates, key=float)
