"""``time_selection.selected_start_time`` against OpenFOAM v2412's own rule
(``src/OpenFOAM/db/Time/Time.C``, ``Foam::Time::setControls``). One test per
row of the owner's table (2026-09-26):

| situation | OpenFOAM | required behaviour |
|---|---|---|
| no ``system/controlDict`` | not an OpenFOAM case | no roots at all |
| ``startFrom`` absent | defaults to ``latestTime`` | same |
| ``startFrom startTime`` with no ``startTime`` | ``FatalIOError`` | refuse by name |
| ``startFrom`` not startTime/firstTime/latestTime | ``FatalIOError`` | refuse by name |
| ``firstTime``/``latestTime`` | ``findTimes``, skipping ``constant`` | same, via the conventions regex |
| ``firstTime``/``latestTime``, no time folders | ``startTime_`` stays its ctor default 0 | ``"0"`` |

cardiacCore has no time concept of its own: it always writes to ``0/`` and
every one of its cases sets ``startFrom startTime; startTime 0;`` explicitly
-- never exercising the "absent" or "malformed" rows. Nothing here invents
time semantics for a non-OpenFOAM folder; the "no controlDict" row is the
seam that keeps such a folder OUT of this function's opinion entirely (see
``selected_start_time``'s own docstring for the owner's rule verbatim, and
``test_provenance_integration.py`` for the ``get_input_roots``-level proof
that "no controlDict" really does mean "no roots at all", not ``"0"``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
from omnidriver.openfoam.mutators import read_foam_entry
from omnidriver.openfoam.time_selection import TimeSelectionError, selected_start_time

_PATTERN = openfoam_case_runtime_conventions().instance_directory_pattern


def _select(case_root: Path) -> str | None:
    return selected_start_time(
        case_root,
        control_dict_relpath="system/controlDict",
        read_value=read_foam_entry,
        instance_directory_pattern=_PATTERN,
    )


def _write_control_dict(case_root: Path, text: str) -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "controlDict").write_text(text)


def test_no_control_dict_answers_none_not_zero(tmp_path: Path) -> None:
    """No ``system/controlDict`` at all: not an OpenFOAM case by the owner's
    rule ("controlDict is how we know an OpenFOAM case exists"). ``None``,
    never the literal ``"0"`` -- that string would be indistinguishable from
    a real, deliberate start time."""
    assert _select(tmp_path) is None


def test_start_from_absent_defaults_to_latest_time(tmp_path: Path) -> None:
    """``Time.C``: ``controlDict_.getOrDefault<word>("startFrom",
    "latestTime")`` -- the comment right above it says "default is to resume
    calculation from 'latestTime'". Not ``startTime``, which today's
    (pre-fix) code wrongly assumed."""
    _write_control_dict(tmp_path, "application cardiacFoam;\n")
    for name in ("0", "0.5", "1"):
        (tmp_path / name).mkdir()

    assert _select(tmp_path) == "1"


def test_start_from_start_time_with_no_start_time_entry_refuses_by_name(tmp_path: Path) -> None:
    """``startFrom startTime;`` with no ``startTime`` entry: real OpenFOAM's
    ``controlDict_.readEntry("startTime", startTime_)`` is a ``FatalIOError``
    when the key is absent -- refused here as ``TimeSelectionError``, not the
    old silent ``"0"``."""
    _write_control_dict(tmp_path, "startFrom startTime;\n")

    with pytest.raises(TimeSelectionError, match="startTime"):
        _select(tmp_path)


def test_start_from_unrecognised_value_refuses_by_name(tmp_path: Path) -> None:
    """``startFrom`` naming anything other than
    ``startTime``/``firstTime``/``latestTime`` is
    ``FatalIOErrorInFunction(controlDict_) << "expected startTime, firstTime
    or latestTime"`` in real OpenFOAM -- refused here by name too."""
    _write_control_dict(tmp_path, "startFrom nextWrite;\n")

    with pytest.raises(TimeSelectionError, match="nextWrite"):
        _select(tmp_path)


def test_first_time_takes_the_first_time_directory_after_constant(tmp_path: Path) -> None:
    """``findTimes`` skips ``constant``; ``firstTime`` takes the first
    directory after it. The conventions regex never matches ``constant`` in
    the first place, so no separate skip is needed here -- it is simply
    never a candidate."""
    _write_control_dict(tmp_path, "startFrom firstTime;\n")
    for name in ("constant", "0", "0.5", "1"):
        (tmp_path / name).mkdir()

    assert _select(tmp_path) == "0"


def test_latest_time_takes_the_last_time_directory(tmp_path: Path) -> None:
    _write_control_dict(tmp_path, "startFrom latestTime;\n")
    for name in ("constant", "0", "0.5", "1"):
        (tmp_path / name).mkdir()

    assert _select(tmp_path) == "1"


@pytest.mark.parametrize("start_from", ["firstTime", "latestTime"])
def test_first_or_latest_time_with_no_time_folders_answers_zero(
    tmp_path: Path, start_from: str,
) -> None:
    """Not a fallback: ``Time``'s own constructor initialises
    ``startTime_(0)``, and when ``findTimes`` returns nothing, neither
    ``setControls``'s ``firstTime`` nor ``latestTime`` branch ever assigns
    ``startTime_`` -- it keeps the constructor's own default. Only
    ``constant/`` exists here, which the conventions regex never matches."""
    _write_control_dict(tmp_path, f"startFrom {start_from};\n")
    (tmp_path / "constant").mkdir()

    assert _select(tmp_path) == "0"
