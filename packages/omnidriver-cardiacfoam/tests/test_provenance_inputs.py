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
#     test_provenance_inputs
#
# Description
#     Canonical input enumeration (Task 2b): which on-disk files a workflow
#     run actually consumes, as seen through cardiacFoam's own
#     CaseProvenanceCapability.
#
#     Moved from core's ``tests/core/test_provenance_inputs.py`` (Phase 2,
#     Milestone 3): this test's own docstring frames it as proving
#     cardiacFoam's ``CaseProvenanceCapability`` excludes mesh-diagnostic
#     byproducts (``constant/C``, ``constant/skewness``) -- a cardiac-specific
#     exclusion rule, not core mechanism. Its generic counterpart,
#     ``test_generic_plugin_still_requires_unknown_files``, stays in core and
#     asserts the opposite: an unclassified file always defaults to
#     required_input.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import default_driver_context
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs


def _paths(components, *, kind: str | None = None) -> set[str]:
    return {c.path for c in components if kind is None or c.kind == kind}


def _write_control_dict(case_root: Path, *, start_from: str, start_time: str = "0") -> None:
    system = case_root / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "controlDict").write_text(
        f"startFrom       {start_from};\nstartTime       {start_time};\n"
        "endTime         1;\ndeltaT          0.01;\n"
    )


def test_system_and_constant_are_required_and_diagnostic_outputs_are_excluded(tmp_path: Path) -> None:
    """cardiacFoam's own CaseProvenanceCapability excludes the mesh-diagnostic
    byproducts nothing reads (I1's worked example)."""
    _write_control_dict(tmp_path, start_from="startTime", start_time="0")
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "electroProperties").write_text("solver monodomain;\n")
    (tmp_path / "constant" / "C").write_bytes(b"mesh-diagnostic-byproduct")
    (tmp_path / "constant" / "skewness").write_bytes(b"mesh-diagnostic-byproduct")

    components = enumerate_case_inputs(
        tmp_path, workflow_dag={"steps": []}, driver_context=default_driver_context(),
    )
    included = _paths(components, kind="case_file")

    assert "system/controlDict" in included
    assert "constant/electroProperties" in included
    assert "constant/C" not in included
    assert "constant/skewness" not in included
