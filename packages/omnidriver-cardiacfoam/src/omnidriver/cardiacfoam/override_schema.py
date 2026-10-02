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
#     override_schema
#
# Description
#     The electro/physics document shape of cardiacFoam's dictionary-entry
#     catalog. Core serializes it; the vocabulary itself is solver knowledge
#     and lives here.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from typing import Any

def dict_entry_catalog(catalog: Any, groups: dict[str, Any]) -> dict[str, Any]:
    """Return the cardiac document shape of the dictionary-entry catalog.

    ``physicsProperties`` is a flat sequence while ``electroProperties`` is
    grouped; that asymmetry mirrors the two OpenFOAM dictionaries this solver
    reads and is deliberately not a core convention. Values are returned
    unserialized -- core owns serialization.
    """
    return {
        "physicsProperties": list(catalog.entries_for("physicsProperties")),
        "electroProperties": {
            group_name: list(entries) for group_name, entries in groups.items()
        },
    }
