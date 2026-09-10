"""Core introspection guarantees, exercised with a neutral plugin."""

from __future__ import annotations

import json
import stat
import tempfile
from pathlib import Path

from omnidriver.core.introspection import _run_state_schema, describe_entry
from omnidriver.core.plugin_interface import generic_openfoam_context


def test_run_state_schema_does_not_advertise_unwritten_action_events_file() -> None:
    schema = _run_state_schema()
    assert "companion_file" not in schema
    assert "action_events.jsonl" not in json.dumps(schema)


def test_neutral_describe_payload_has_no_domain_catalog_vocabulary() -> None:
    """Core namespaces plugin catalogs without inventing cardiac names."""
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
        case_root = cases_root / "minimalCase"
        (case_root / "system").mkdir(parents=True)
        (case_root / "constant").mkdir(parents=True)
        (case_root / "system" / "controlDict").write_text(
            "FoamFile{version 2.0; format ascii; class dictionary; object controlDict;}\n"
            "application myGenericSolver;\nstartFrom startTime;\nstartTime 0;\n"
            "stopAt endTime;\nendTime 1;\ndeltaT 0.1;\n"
            "writeControl timeStep;\nwriteInterval 10;\n"
        )
        allrun = case_root / "Allrun"
        allrun.write_text("#!/bin/sh\necho generic-allrun-ran\n")
        allrun.chmod(allrun.stat().st_mode | stat.S_IEXEC)

        payload = describe_entry(
            "minimalCase",
            overrides={"cases_root": str(cases_root)},
            driver_context=generic_openfoam_context(),
        )

    assert payload["plugin_catalogs"] == {}
    assert "ionic_model_catalog" not in payload
    assert "active_tension_catalog" not in payload
