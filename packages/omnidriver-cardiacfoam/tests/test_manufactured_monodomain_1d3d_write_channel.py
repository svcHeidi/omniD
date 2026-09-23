"""Phase 3 Task 6: `manufactured_monodomain_1d3d` -- the `blockMeshDict.3D`
-> `.active` copy convention stays a direct write; only the block-mesh
rewrite that follows it, `deltaT`/`endTime`, and any electro overrides move
onto the channel. The `purkinjeGraph.<id>` copy (a source artifact) is
untouched either way.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import manufactured_monodomain_1d3d as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import (
    digests,
    write_control_dict,
    write_electro_properties,
    write_physics_properties,
)

_RELPATHS = (
    "constant/electroProperties",
    "system/controlDict",
    "system/blockMeshDict.3D.active",
    "constant/purkinjeGraph",
)

_BLOCK_MESH_3D_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 10 10) simpleGrading (1 1 1)\n"
    ");\n"
)

# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`.
_DIGESTS_BEFORE = {
    "constant/electroProperties": "a981e6bc5b256ebdfcd35de4a0ea035b80134a53c2fc0e2ff9953e73bf513ab4",
    "system/controlDict": "f458e4b7e0c13e76eeed76e1900d430b560842f61654ef42a1d8442f0309cc08",
    "system/blockMeshDict.3D.active": "67887ca4ecee0781cec9107857202b899868a1b11893b303d8e9b3124deaf2fb",
    "constant/purkinjeGraph": "f1a5ff03a984552153d7a914f0959ef57c690b199c12c738012a5bb70312df16",
}


def _write_case(root: Path) -> None:
    write_electro_properties(root)
    write_physics_properties(root)
    write_control_dict(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "blockMeshDict.3D").write_text(_BLOCK_MESH_3D_TEXT)
    (root / "constant" / "purkinjeGraph.nodes021").write_text("graph-nodes021\n")


def _case() -> CaseConfig:
    return CaseConfig(case_id="20", params={"graph_id": "nodes021", "cells": 20, "dt": 3.50e-4})


def _kwargs() -> dict:
    return dict(
        electro_property_overrides={"monodomainSolverCoeffs.solutionAlgorithm": "implicitEuler"},
        end_time=0.1,
    )


class TestManufacturedMonodomain1d3dWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-1d3d-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_apply_case_current_bytes(self) -> None:
        root = self.tmp / "apply"
        _write_case(root)
        tut._apply_case(root, _case(), **_kwargs())
        self.assertEqual(digests(root, *_RELPATHS), _DIGESTS_BEFORE)

    def test_plan_case_reproduces_apply_case_bytes_exactly(self) -> None:
        apply_root = self.tmp / "apply2"
        plan_root = self.tmp / "plan"
        _write_case(apply_root)
        _write_case(plan_root)

        tut._apply_case(apply_root, _case(), **_kwargs())
        record = tut._plan_case(plan_root, _case(), **_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        self.assertEqual(digests(plan_root, *_RELPATHS), digests(apply_root, *_RELPATHS))
        # blockMeshDict.3D itself (the un-rewritten source) must stay
        # untouched -- only the .active copy is rewritten.
        self.assertEqual(
            (plan_root / "system" / "blockMeshDict.3D").read_text(), _BLOCK_MESH_3D_TEXT,
        )


if __name__ == "__main__":
    unittest.main()
