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
#     test_run_document_config_schema
#
# Description
#     Tests plugin-declared RunDocument.config schema validation.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Plugin-declared RunDocument.config schema validation on the ingestion path:
an agent-authored document read off disk, checked in ``run_document_exec``
against the plugin's own declared schema.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.planning_types import StrictDiagnostic
from omnidriver.cardiacfoam.run_document_config import _read_physics_type
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


# cardiacFoam's profile requires org.omnidriver.openfoam.environment, so both are composed.
def _context():
    return _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(),
        source="test:run_document_config_schema",
    )


def test_cardiac_plugin_declares_a_config_schema() -> None:
    context = _context()
    # cardiacFoam is the most specific provider, last in the ordered stack.
    schema = context.providers[-1].get_run_document_config_schema()
    assert schema["required"] == ["anatomy", "physics", "stimulus", "solver"]


# The emission path (build_run_document_config during strict_plan) is not
# violated here: that needs a staged broken case; ingestion covers the contract.


def _document_json(config: dict) -> dict:
    return {
        "version": "3",
        "id": "ingested",
        "name": "ingested",
        "status": "planned",
        "config": config,
        "configurationSource": "document",
        "launch": {"caseRoot": "/nonexistent/case", "outputDir": "/nonexistent/case/out"},
        "workflowDag": {
            "schema_version": "1",
            "step_status_values": [
                "pending", "running", "completed", "failed", "skipped",
            ],
            "steps": [{
                "id": "solve", "command": "Allrun", "args": [], "cwd": ".",
                "depends_on": [], "produces": [], "consumes": [],
                "retry_policy": {}, "command_display": "Allrun",
            }],
        },
    }


def _ingest(config: dict) -> tuple["StrictDiagnostic", ...]:
    """Load a hand-authored document off disk and adapt it for execution."""
    from omnidriver.core.runtime.run_document_exec import (
        build_execution_inputs,
        load_run_document,
    )

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "run.json"
        path.write_text(json.dumps(_document_json(config)))
        run_doc = load_run_document(path)
    _inputs, diagnostics = build_execution_inputs(
        run_doc, driver_context=_context(),
    )
    return diagnostics


def test_ingested_document_is_checked_against_the_plugin_config_schema() -> None:
    """``tissue`` has a closed enum only in the plugin schema, so this isolates that gate."""
    diagnostics = _ingest({
        "anatomy": {},
        "physics": {"tissue": "notATissue"},
        "stimulus": {},
        "solver": {},
    })
    violations = [
        d for d in diagnostics if d.code == "plugin_config_schema_violation"
    ]
    assert violations, diagnostics
    assert violations[0].field == "physics.tissue"
    assert "notATissue" in violations[0].message


def test_ingested_document_with_a_schema_valid_config_raises_no_violation() -> None:
    diagnostics = _ingest({
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    })
    assert not [
        d for d in diagnostics if d.code == "plugin_config_schema_violation"
    ], diagnostics


def test_read_physics_type_ignores_a_nested_type_key(tmp_path):
    path = tmp_path / "physicsProperties"
    path.write_text(
        "FoamFile{ version 2.0; format ascii; class dictionary; object physicsProperties; }\n"
        "someSubBlock\n{\n    type notTheRealAnswer;\n}\n"
        "type monodomain;\n"
    )
    assert _read_physics_type(path) == "monodomain"


def test_read_physics_type_returns_none_when_file_missing(tmp_path):
    assert _read_physics_type(tmp_path / "nope") is None
