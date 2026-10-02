"""``sweep-plan`` must answer in its own contract, like ``plan --strict``."""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.runtime.sweep_runner import sweep_plan
from omnidriver.core.plugin_interface import driver_context
from plugins.conformance_toy import write_toy_native_case
from plugins.e2e_record_plugin import E2ERecordPlugin

_CTX = driver_context(E2ERecordPlugin(), source="test:sweep-plan")


def _spec(cases_root: Path) -> dict:
    return {
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {"mode": "zip", "independent": {"number_cells": [2, 3]}},
    }


def test_a_malformed_spec_is_reported_structurally(tmp_path):
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text("{ not json")

    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    assert report["case_count"] == 0
    assert report["cases"] == []
    assert "spec_error" in report
    json.dumps(report)  # must be serialisable


def test_a_valid_spec_reports_no_spec_error(tmp_path):
    spec_path = tmp_path / "sweep.json"
    write_toy_native_case(tmp_path / "native")
    spec_path.write_text(json.dumps(_spec(tmp_path / "native")))
    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)
    assert "spec_error" not in report
