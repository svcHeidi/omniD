"""Parity proof: the corrected ``selected_start_time`` picks the same start
folder, for every real native cardiacFOAM ``controlDict``, as the pre-fix
code did (final review M5's restored version, before the 2026-09-26 owner
correction). Supplied only through ``OMNIDRIVER_NATIVE_TUTORIALS``, never
discovered -- FAILS, not skips, when it is unset (CLAUDE.md's native-tree
row).

All 17 native ``controlDict``s set ``startFrom`` explicitly (16
``startTime``, 1 ``latestTime``), and every one that sets ``startFrom
startTime`` also sets ``startTime`` -- so none of them ever exercises the
rows this fix actually changes (``startFrom`` absent, or malformed): the two
implementations can only disagree by construction if one of those facts
stops holding, which this test would then catch.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
from omnidriver.openfoam.mutators import read_foam_entry
from omnidriver.openfoam.time_selection import selected_start_time

pytestmark = pytest.mark.native

_PATTERN = openfoam_case_runtime_conventions().instance_directory_pattern


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is "
            "never discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _native_case_roots(root: Path) -> list[Path]:
    """Every native case with a ``system/controlDict``, excluding
    ``results/`` (the same exclusion the task's own evidence-gathering
    used)."""
    return sorted(
        {
            p.parent.parent
            for p in root.rglob("system/controlDict")
            if "results" not in p.relative_to(root).parts
        }
    )


def _pre_fix_selected_start_time(
    case_root: Path, *, control_dict_relpath: str, read_value, instance_directory_pattern: str,
) -> str:
    """The restored-after-M5-revert implementation, verbatim (before the
    2026-09-26 owner correction): missing ``controlDict``/``startTime``
    silently answered ``"0"``, and ``startFrom`` absent defaulted to
    ``"startTime"`` -- both wrong per OpenFOAM's own ``Time::setControls``,
    but this is what every native case's start folder was computed with
    until now. Kept here only as this test's own fixed reference point, not
    reintroduced anywhere real."""
    default = "0"
    control_dict = case_root / control_dict_relpath
    if not control_dict.is_file():
        return default

    start_from = (read_value(control_dict, "startFrom") or "startTime").strip()
    if start_from not in {"latestTime", "firstTime"}:
        value = read_value(control_dict, "startTime")
        return value.strip() if value is not None else default

    pattern = re.compile(instance_directory_pattern)
    candidates: list[str] = []
    try:
        children = case_root.iterdir()
    except OSError:
        return default
    for child in children:
        if not child.is_dir():
            continue
        if not pattern.fullmatch(child.name):
            continue
        candidates.append(child.name)
    if not candidates:
        return default
    selector = max if start_from == "latestTime" else min
    return selector(candidates, key=float)


def test_every_native_case_gets_the_same_start_folder_before_and_after_the_fix():
    root = _native_tutorials_root()
    cases = _native_case_roots(root)
    assert len(cases) == 17, (
        f"expected 17 native cases with a system/controlDict (excluding results/), "
        f"found {len(cases)}: {cases}"
    )

    mismatched = []
    for case_root in cases:
        before = _pre_fix_selected_start_time(
            case_root,
            control_dict_relpath="system/controlDict",
            read_value=read_foam_entry,
            instance_directory_pattern=_PATTERN,
        )
        after = selected_start_time(
            case_root,
            control_dict_relpath="system/controlDict",
            read_value=read_foam_entry,
            instance_directory_pattern=_PATTERN,
        )
        if before != after:
            mismatched.append((case_root, before, after))

    assert mismatched == [], (
        f"the corrected selected_start_time disagrees with the pre-fix "
        f"answer for one or more native cases: {mismatched}"
    )


def test_every_native_control_dict_sets_start_from_explicitly():
    """The evidence this parity proof relies on: every native case sets
    ``startFrom`` explicitly (never absent), so the "absent defaults to
    latestTime, not startTime" fix never fires for any of them -- the
    parity test above proves agreement, not that this fix is untested."""
    root = _native_tutorials_root()
    cases = _native_case_roots(root)
    assert cases, "no native case found, so this proves nothing"

    missing_start_from = [
        case_root for case_root in cases
        if read_foam_entry(case_root / "system" / "controlDict", "startFrom") is None
    ]
    assert missing_start_from == []
