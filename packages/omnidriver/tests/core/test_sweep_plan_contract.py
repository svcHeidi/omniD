"""Structured success and failure results from ``sweep-plan``."""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.runtime.sweep_runner import sweep_plan
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin

_CTX = driver_context(MinimalTestPlugin(), source="test:sweep-plan")

_SPEC = {
    "base": {},
    "sweep": {
        "mode": "zip",
        "independent": {
            "axisA": ["valueA", "valueB"],
        },
    },
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
    spec_path.write_text(json.dumps(_SPEC))
    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)
    assert "spec_error" not in report
