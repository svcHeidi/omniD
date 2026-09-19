#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_units_have_one_home
#
# Description
#     A unit is declared in the unit field, not asserted in prose beside it.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""A unit is declared in the `unit` field, not asserted in prose beside it.

``DictEntry`` carries a structured ``unit``, and most of this catalogue uses it.
Some entries instead state the unit only inside their description, as a
bracketed token -- which reads identically to a human and is invisible to
everything else. A unit that exists only in prose cannot be compared against
anything, converted, or checked.

That matters here specifically. cardiacFOAM describes electrode positions as
"position vector [m]" while cardiacCore's ``operations/electrodes.py`` carries a
caller-declared ``coordinate_unit`` and states "No metre-to-millimetre
assumption is made" -- and `newVtkUnstructuredToFoam` exists partly to apply
``-scale 0.001`` because meshes are commonly built in millimetres. Nothing
converts between the two, and nothing can, while one side's unit is a sentence.
A millimetre case feeding cardiacCore-derived coordinates into cardiacFOAM runs
clean and produces a pseudo-ECG potential off by a factor of a thousand.

This guard does not fix that seam. It makes the cardiacFOAM half of it
machine-readable, which is the precondition for a check that could.

Measured 2026-09-19 over all 173 entries: 17 state the unit both ways and
**none** of those 17 disagree, so the convention is sound and this guard
pins it rather than imposing something new.
"""

from __future__ import annotations

import re

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(CardiacFoamPlugin(), source="test:units_have_one_home")

#: A bracketed token is read as a unit claim unless it contains a comma or a
#: space. Measured over the whole catalogue, the only bracketed token that is
#: not a unit is ``[min, max]``; every other one is (`[s]`, `[m]`, `[ms]`,
#: `[V]`, `[S]`, `[m/s]`, `[A/m³]`, `[1/m]`, `[F/m²]`, `[s^(-1/2)]`).
_BRACKETED = re.compile(r"\[([^\],\s]{1,20})\]")


def _claimed_in_prose(entry) -> str | None:
    match = _BRACKETED.search(entry.description or "")
    return match.group(1) if match else None


def test_a_unit_stated_in_prose_is_also_declared() -> None:
    entries = _CTX.capabilities.dictionaries.entries()
    assert len(entries) > 100, (
        f"expected the full cardiacFOAM catalogue, got {len(entries)} entries -- "
        "this guard is not looking where it thinks"
    )

    undeclared = [
        f"{entry.driver_path}  (prose says [{_claimed_in_prose(entry)}], unit unset)"
        for entry in entries
        if _claimed_in_prose(entry) and not getattr(entry, "unit", None)
    ]

    assert undeclared == [], (
        "these entries state a unit in their description and nowhere a machine "
        "can read it:\n  " + "\n  ".join(undeclared)
        + "\n\nSet DictEntry.unit. The description may keep the bracketed token "
        "for a human reader, but it may not be the only place the unit exists."
    )


def test_prose_and_declared_units_agree() -> None:
    """Two statements of one fact must at least be checked against each other.

    The bracketed token is allowed to remain -- it reads well in a catalogue
    dump -- but it is no longer an independent truth, because this fails the
    moment it drifts from the field.
    """
    entries = _CTX.capabilities.dictionaries.entries()

    disagreements = [
        f"{entry.driver_path}: prose says [{_claimed_in_prose(entry)}], unit is {entry.unit!r}"
        for entry in entries
        if _claimed_in_prose(entry)
        and getattr(entry, "unit", None)
        and _claimed_in_prose(entry) != entry.unit
    ]

    assert disagreements == [], (
        "a unit is stated twice and the two disagree:\n  " + "\n  ".join(disagreements)
    )
