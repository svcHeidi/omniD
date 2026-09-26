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
#     config_schema
#
# Description
#     The cardiacFoam plugin's RunDocument.config JSON Schema.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""The cardiacFoam plugin's RunDocument.config JSON Schema.

Returned by CardiacFoamPlugin.get_run_document_config_schema() and validated
by core via jsonschema.validate() against whatever config the plugin built.
"""
from __future__ import annotations

from typing import Any

CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["anatomy", "physics", "stimulus", "solver"],
    "properties": {
        "anatomy": {"type": "object"},
        "physics": {"$ref": "#/$defs/physicsSlice"},
        "stimulus": {"type": "object"},
        "solver": {"type": "object"},
    },
    "additionalProperties": False,
    "$defs": {
        "physicsSlice": {
            "type": "object",
            "description": (
                "Physics-phase configuration as flat slot-keys. The complete "
                "authoritative key catalogue is omnidriver.dict_entries."
            ),
            "properties": {
                "myocardiumSolver": {
                    "type": "string",
                    "description": "Top-level myocardium solver selector.",
                },
                "ionicModel": {
                    "type": "string",
                    "description": "Ionic cell model selector.",
                },
                "tissue": {
                    "type": "string",
                    "enum": ["epicardialCells", "mCells", "endocardialCells", "myocyte"],
                },
                "ionicHeterogeneity.field": {"type": "string"},
                "ionicHeterogeneity.mode": {
                    # Corrected 2026-09-26 (catalog drift fix, final review
                    # AB Q7): native c7d6dd551 removed the transmuralBands
                    # mode (and endoMInterface/mEpiInterface, which only it
                    # used); only namedRegions and cellZoneRegions remain
                    # (ionicHeterogeneityOrchestrator.C).
                    "type": "string",
                    "enum": ["namedRegions", "cellZoneRegions"],
                },
                "ionicHeterogeneity.transitionWidth": {"type": ["string", "number"]},
                "ionicHeterogeneity.transitionMode": {
                    "type": "string",
                    "enum": ["blend", "hard"],
                },
                "ionicHeterogeneity.smoothing": {
                    "type": "string",
                    "enum": ["smoothstep"],
                },
            },
            "additionalProperties": True,
        },
    },
}


def get_run_document_config_schema() -> dict[str, Any]:
    """Return the cardiac plugin's RunDocument.config schema."""
    return CONFIG_SCHEMA
