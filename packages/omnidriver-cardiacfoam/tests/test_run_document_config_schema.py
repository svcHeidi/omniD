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
#     Tests plugin-declared RunDocument.config schema validation (P2.2).
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Plugin-declared RunDocument.config schema validation (P2.2).

Covers the *ingestion* path: an agent-authored document read off disk,
checked in ``run_document_exec`` against the plugin's own declared schema.
The symmetric *emission* path (``run_document_adapter``, a plugin-built
config checked the same way against a document-sourced spec) is exercised
by a real case-folder entry, not by a registered factory tutorial --
cardiacFoam has none left (tutorials-are-pointers step C) -- see the note
below the schema-declaration test for where that leaves this file's
coverage of it.
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


# This module asserts the *cardiac* plugin's config schema, so it names that
# plugin rather than asking the ambient default -- which has no single answer
# once a second adapter is installed (future/ENVIRONMENT_CONTRACT.md §12).
# Composes the environment adapter too (Task 9): cardiacFoam's profile now
# declares `requires: [org.omnidriver.openfoam.environment]`, unmet by a
# single-provider stack.
def _context():
    return _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(),
        source="test:run_document_config_schema",
    )


def test_cardiac_plugin_declares_a_config_schema() -> None:
    context = _context()
    # `.plugin` was the retired single-plugin field; cardiacFoam is the most
    # specific provider, last in the ordered stack.
    schema = context.providers[-1].get_run_document_config_schema()
    assert schema["required"] == ["anatomy", "physics", "stimulus", "solver"]


# The planning-side counterpart of this contract (build_run_document_config
# violating its own declared schema, checked during strict_plan) used a
# synthetic factory tutorial to reach a document-sourced spec. cardiacFoam
# has no factory tutorial to be one any more (tutorials-are-pointers step
# C) -- build_run_document_config's real parser (run_document_config.py)
# is not dead, though: it still runs for a real case-folder entry whose
# dict files are already materialized (spec.metadata["generic_case"] is
# then False), the shape a generic sweep's per-case audit exercises
# (test_sweep_runner.py). Testing a *violation* that way would mean staging
# a real, broken case -- more than this schema-symmetry contract needs when
# the tests below already cover it end-to-end via ingestion, which needs no
# spec/entry at all.


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
    """An agent-authored config that violates the plugin's own schema must be
    rejected at *ingestion*, with the same diagnostic code the emission path
    uses. The ingestion path is the untrusted one: before this gate it saw
    only ``validate_run`` and never consulted the plugin schema at all.

    ``tissue`` carries a closed enum in the cardiac plugin's config schema
    but no catalog enum that ``validate_run`` would independently reject, so
    an out-of-enum value here isolates the plugin-schema gate.
    """
    # Corrected 2026-09-20 (Phase 0 Task 10): `build_execution_inputs` used
    # to serialize diagnostics as plain `{level, code, message, field}`
    # dicts (`run_document_exec._diag`); it now returns the canonical
    # `core.planning_types.StrictDiagnostic` dataclass, so these are
    # attribute lookups, not subscripts.
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
    """The gate must not fire on a config the plugin schema accepts (the
    all-empty phase config a core generic case emits)."""
    diagnostics = _ingest({
        "anatomy": {}, "physics": {}, "stimulus": {}, "solver": {},
    })
    assert not [
        d for d in diagnostics if d.code == "plugin_config_schema_violation"
    ], diagnostics


def test_read_physics_type_ignores_a_nested_type_key(tmp_path):
    """A nested block's own 'type' key must not shadow the real top-level one.

    The pre-migration scanner matches the first line starting with 'type'
    anywhere in the file, with no nesting awareness -- a hypothetical
    nested block declared before the real entry would silently win.
    """
    path = tmp_path / "physicsProperties"
    path.write_text(
        "FoamFile{ version 2.0; format ascii; class dictionary; object physicsProperties; }\n"
        "someSubBlock\n{\n    type notTheRealAnswer;\n}\n"
        "type monodomain;\n"
    )
    assert _read_physics_type(path) == "monodomain"


def test_read_physics_type_returns_none_when_file_missing(tmp_path):
    assert _read_physics_type(tmp_path / "nope") is None
