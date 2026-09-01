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
#     test_workflow_dag_filesystem_ingest
#
# Description
#     Tests workflow dag filesystem ingest logic and specification contracts.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Tests for filesystem case workflow ownership.

Plain case folders are owned by their on-disk Allrun. Registry discovery may
still find a non-runnable marked folder, but it must not invent a
workflow_dag unless Allrun exists.

Phase 2 Task M2: ``test_variant_electro_properties_case_is_discoverable_and_runnable``
moved to
packages/omnidriver-cardiacfoam/tests/test_workflow_dag_filesystem_ingest.py
-- it asserts cardiacFoam's own electroProperties-variant case marker. The
two tests kept here assert core's own DAG-synthesis rule (Allrun present ->
single-step DAG; Allrun absent -> None), independent of what marks a folder
a case at all, so ``_write_case_files`` now writes ``system/controlDict`` +
``constant/`` -- the two filesystem entries GenericOpenFOAMPlugin's own
profile declares (role ``openfoam.control_dict`` / ``openfoam.case_directory``,
see generic-plugin.yaml) -- instead of cardiacFoam's electroProperties/
physicsProperties. A local ``_NeutralFilesystemMarkerPlugin`` declares those
two paths as its ``has_case_marker`` (GenericOpenFOAMPlugin itself declares
none, so a bare folder with no Allrun would otherwise not be discoverable at
all) and wires ``make_generic_case_spec`` into its tutorial catalog -- the
same core-owned factory ``resolve_entry`` already falls back to when no
marker matches, so both branches behave identically and no cardiac
vocabulary is reachable.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.runtime.generic_case import make_generic_case_spec
from omnidriver.core.runtime.registry import load_tutorial_spec, resolve_entry
from omnidriver.core.plugin_interface import driver_context as _driver_context


class _NeutralFilesystemMarkerPlugin(GenericOpenFOAMPlugin):
    """A case marker built only from filesystem entries core itself owns.

    ``system/controlDict`` + a ``constant/`` directory are true of every
    OpenFOAM case regardless of solver (see generic-plugin.yaml's own
    case_profile.dictionaries) -- carrying no cardiac vocabulary, unlike
    cardiacFoam's electroProperties marker.
    """

    def has_case_marker(self, case_root: Path) -> bool:
        return (
            (case_root / "system" / "controlDict").is_file()
            and (case_root / "constant").is_dir()
        )

    def get_tutorial_catalog(self):
        # resolve_entry() looks up "make_generic_case_spec" in the selected
        # plugin's own tutorial catalog once has_case_marker() is True (see
        # registry.py); wire it to the same core factory the no-marker
        # branch already falls back to, so which branch runs makes no
        # behavioural difference here.
        catalog = dict(super().get_tutorial_catalog())
        catalog["make_generic_case_spec"] = make_generic_case_spec
        return catalog


_CTX = _driver_context(
    _NeutralFilesystemMarkerPlugin(),
    source="test:workflow_dag_filesystem_ingest",
)


class TestFilesystemCaseWorkflowOwnership(unittest.TestCase):
    """Filesystem case folders own their run definition through Allrun."""

    def _write_case_files(self, case_root: Path) -> None:
        (case_root / "constant").mkdir(parents=True, exist_ok=True)
        (case_root / "system").mkdir(parents=True, exist_ok=True)
        (case_root / "system" / "controlDict").write_text("")

    def test_filesystem_case_with_allrun_uses_allrun_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tutorials_root = Path(temp_dir)
            case_root = tutorials_root / "myCase"
            self._write_case_files(case_root)
            (case_root / "Allrun").write_text("#!/bin/sh\n")

            spec = load_tutorial_spec(
                "myCase",
                overrides={"tutorials_root": tutorials_root},
                driver_context=_CTX,)

            dag = spec.metadata.get("workflow_dag")
            self.assertEqual(
                dag,
                {"steps": [{"id": "run", "command": "Allrun", "depends_on": []}]},
            )

    def test_filesystem_case_without_allrun_has_no_workflow_dag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tutorials_root = Path(temp_dir)
            case_root = tutorials_root / "bareCase"
            self._write_case_files(case_root)

            spec = load_tutorial_spec(
                "bareCase",
                overrides={"tutorials_root": tutorials_root},
                driver_context=_CTX,)

            dag = spec.metadata.get("workflow_dag")
            self.assertIsNone(dag, "workflow_dag must be None when Allrun is absent")


if __name__ == "__main__":
    unittest.main()
