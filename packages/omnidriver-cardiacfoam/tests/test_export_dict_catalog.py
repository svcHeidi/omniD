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
#     test_export_dict_catalog
#
# Description
#     Tests export dict catalog logic and specification contracts.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Tests for the dict-catalog exporter.

It fans each ``DictEntry`` into one record per declared phase, stamped with that bucket's ``phase`` plus the full ``phases`` list."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from omnidriver.core.specs.paths import repo_root_default

REPO = repo_root_default()
SCRIPT = REPO / "scripts" / "export-dict-catalog.py"
# The exporter runs in a child interpreter that cannot be handed a DriverContext,
# and with several adapters installed there is no ambient default, so name it.
PLUGIN = ("--plugin", "cardiacfoam")


def test_exporter_writes_grouped_json(tmp_path):
    out = tmp_path / "catalog.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out), *PLUGIN],
        cwd=REPO, check=True,
    )
    data = json.loads(out.read_text())
    assert data["version"] == "1"
    assert set(data["phases"].keys()) == {
        "anatomy", "physics", "stimulus", "solver"
    }
    physics = data["phases"]["physics"]
    assert "entries" in physics and len(physics["entries"]) > 0
    first = physics["entries"][0]
    assert {"driver_path", "description", "unit",
            "typical_value", "source_refs", "phase", "phases"} <= first.keys()
    assert first["phase"] == "physics"
    assert "physics" in first["phases"]
    assert "ionic_models" in data
    assert "active_tension_models" in data


def test_multi_phase_entry_appears_in_every_declared_phase(tmp_path):
    out = tmp_path / "catalog.json"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out), *PLUGIN],
        cwd=REPO, check=True,
    )
    data = json.loads(out.read_text())

    def paths_in(phase):
        return {e["driver_path"] for e in data["phases"][phase]["entries"]}

    multi = [
        e for phase in data["phases"] for e in data["phases"][phase]["entries"]
        if len(e["phases"]) > 1
    ]
    assert multi, "expected at least one multi-phase entry after A2 classification"
    sample = multi[0]
    for ph in sample["phases"]:
        assert sample["driver_path"] in paths_in(ph), (
            f"{sample['driver_path']} declared phases={sample['phases']} "
            f"but missing from bucket {ph!r}"
        )
