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
#     test_report_catalog_export
#
# Description
#     Tests report catalog export logic and specification contracts.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Tests for the report-catalog exporter, which serializes report definitions to JSON and never
substitutes ``{port}`` or ``{kind}``, so the report backend is swappable. The v1 URL template is
``http://localhost:{port}/{kind}``, with no ``{runId}``; ``applicable_when`` is flat key-equality."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from omnidriver.core.specs.paths import repo_root_default

REPO = repo_root_default()
SCRIPT = REPO / "scripts" / "export-report-catalog.py"


def _run(out_path: Path) -> dict:
    subprocess.run(
        # The ambient default is ambiguous once a second adapter is installed, so name the plugin.
        [sys.executable, str(SCRIPT), "--out", str(out_path), "--plugin", "cardiacfoam"],
        cwd=REPO,
        check=True,
    )
    return json.loads(out_path.read_text())


# ---------------------------------------------------------------------------
# Schema / shape
# ---------------------------------------------------------------------------


def test_exporter_writes_versioned_report_list(tmp_path):
    data = _run(tmp_path / "r.json")
    assert data["version"] == "1"
    assert isinstance(data["reports"], list)
    assert len(data["reports"]) >= 1, "v1 must ship at least the stub entry"
    sample = data["reports"][0]
    expected = {
        "id",
        "title",
        "kind",
        "url_template",
        "applicable_when",
        "show_by_default",
    }
    assert expected <= sample.keys(), (
        f"missing keys: {expected - sample.keys()}"
    )


def test_stub_entry_present(tmp_path):
    """The offline-bundled stub keeps the section working when 4Dpapers is not running."""
    data = _run(tmp_path / "r.json")
    ids = {r["id"] for r in data["reports"]}
    assert "stub" in ids, f"expected 'stub' entry; got {sorted(ids)}"
    stub = next(r for r in data["reports"] if r["id"] == "stub")
    assert stub["url_template"] == "/reports/stub.html"
    assert stub["kind"] == "iframe"


def test_v1_url_templates_have_no_runid_placeholder(tmp_path):
    """4Dpapers v1 does not route by run; a leaked ``{runId}`` would force consumers to invent one."""
    data = _run(tmp_path / "r.json")
    for r in data["reports"]:
        assert "{runId}" not in r["url_template"], (
            f"report {r['id']!r} leaked {{runId}} into v1 url_template"
        )


def test_remote_entries_use_4dpapers_template(tmp_path):
    """At least one non-stub entry targets the real 4Dpapers backend, not just the bundled fallback."""
    data = _run(tmp_path / "r.json")
    remote = [r for r in data["reports"] if r["id"] != "stub"]
    assert remote, "expected at least one 4Dpapers-backed report entry"
    for r in remote:
        assert r["url_template"].startswith("http://localhost:{port}/"), (
            f"report {r['id']!r} url_template does not target the "
            f"4Dpapers backend: {r['url_template']!r}"
        )
