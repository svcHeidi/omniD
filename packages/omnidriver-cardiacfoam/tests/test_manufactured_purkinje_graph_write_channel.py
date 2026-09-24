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
#     test_manufactured_purkinje_graph_write_channel
#
# Description
#     Phase 3 Task 7: `manufactured_purkinje_graph` is the second tutorial
#     Task 6 could not migrate. Its own write (a `purkinjeGraph.<id>` ->
#     `purkinjeGraph` copy) is classified as a genuine source artifact, not
#     a `RenderedFile` -- see `_apply_case`'s
#     own docstring for the argument -- and correctly stays a direct write
#     with zero `commit_case_write` calls, a declared exception rather than
#     an open bypass.
#
#     Also locks in this task's `_ensure_mesh` finding: that private helper
#     shelled out to `blockMesh` directly, had zero callers anywhere in this
#     repository, and duplicated the "mesh" `workflow_dag` step already
#     declared in this same module's `make_spec` -- the real, executed
#     mesh-authoring mechanism. Deleted rather than migrated; there was
#     nothing live to migrate.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import manufactured_purkinje_graph
from omnidriver.core.runtime.models import CaseConfig


class TestManufacturedPurkinjeGraphApplyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-purkinje-graph-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_apply_case_copies_the_named_graph_verbatim(self) -> None:
        case_root = self.tmp
        (case_root / "constant").mkdir()
        graph_text = "FoamFile\n{\n}\nrootNode\n0;\n"
        (case_root / "constant" / "purkinjeGraph.g1").write_text(graph_text)

        manufactured_purkinje_graph._apply_case(
            case_root, CaseConfig(case_id="g1", params={"graph_id": "g1"}),
        )

        self.assertEqual(
            (case_root / "constant" / "purkinjeGraph").read_text(), graph_text,
        )

    def test_apply_case_refuses_a_missing_graph(self) -> None:
        case_root = self.tmp
        (case_root / "constant").mkdir()
        with self.assertRaises(FileNotFoundError):
            manufactured_purkinje_graph._apply_case(
                case_root, CaseConfig(case_id="missing", params={"graph_id": "missing"}),
            )

    def test_no_plan_case_is_supplied(self) -> None:
        """This tutorial has no `ParameterAssignment`-shaped mutation at all
        -- its `TutorialSpec` correctly supplies no `plan_case`, unlike the
        other twelve tutorials this phase migrated."""
        spec = manufactured_purkinje_graph.make_spec(cases_root=self.tmp)
        self.assertIsNone(spec.plan_case)


class TestEnsureMeshWasDeadCodeNowDeleted(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-purkinje-graph-mesh-step-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_ensure_mesh_no_longer_exists(self) -> None:
        self.assertFalse(hasattr(manufactured_purkinje_graph, "_ensure_mesh"))

    def test_the_mesh_step_it_duplicated_is_still_declared(self) -> None:
        """The reason `_ensure_mesh` was dead: this "mesh" step already
        authors `constant/polyMesh` via the real, executed `workflow_dag`
        mechanism (`workflow_orchestrator.py`)."""
        spec = manufactured_purkinje_graph.make_spec(cases_root=self.tmp)
        steps = spec.metadata["workflow_dag"]["steps"]
        by_id = {step["id"]: step for step in steps}
        self.assertEqual(by_id["mesh"]["command"], "blockMesh")
        self.assertEqual(by_id["solve"]["depends_on"], ["mesh"])


if __name__ == "__main__":
    unittest.main()
