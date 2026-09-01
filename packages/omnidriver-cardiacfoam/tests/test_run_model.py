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
#     test_run_model
#
# Description
#     Tests that the cardiac plugin's own config schema
#     (``omnidriver.cardiacfoam.config_schema.CONFIG_SCHEMA``) still enforces
#     the physics-phase vocabulary (heterogeneity mode, tissue).
#
#     Moved from core's ``tests/core/test_run_model.py`` (Phase 2, Milestone
#     3): the physics-phase vocabulary moved to the cardiac plugin's own
#     config schema (P2.2) -- core's run-document schema no longer enforces
#     it, so these validate against the plugin schema directly. Their core
#     counterpart, ``test_schema_still_allows_unlisted_physics_keys``, stays
#     in core and proves core's schema is deliberately open.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import jsonschema
import pytest

from omnidriver.cardiacfoam.config_schema import CONFIG_SCHEMA


def _valid_run_dict():
    return {
        "version": "3",
        "id": "run-0001",
        "name": "demo",
        "createdAt": "2026-04-20T10:00:00Z",
        "lastModified": "2026-04-20T10:00:00Z",
        "status": "draft",
        "config": {
            "anatomy": {},
            "physics": {},
            "stimulus": {},
            "solver": {},
        },
        "validation": {},
        "resolvedEntry": None,
        "workflowDag": None,
        "workflowState": None,
        "launch": None,
        "expectedArtifacts": [],
        "terminalStatusValues": ["completed", "failed"],
    }


def test_schema_rejects_unknown_heterogeneity_mode() -> None:
    doc = _valid_run_dict()
    doc["config"]["physics"] = {"ionicHeterogeneity.mode": "bogusMode"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc["config"], CONFIG_SCHEMA)


def test_schema_rejects_unknown_tissue() -> None:
    doc = _valid_run_dict()
    doc["config"]["physics"] = {"tissue": "notATissue"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc["config"], CONFIG_SCHEMA)
