"""Phase 3 Task 6: `manufactured_eikonal_ecg`'s hex-family path -- entry
overrides (including the dynamic `ecgDomains.ECG.electrodePositions.<name>`
path) and a block-mesh rewrite move onto the channel. The optional
`grad_scheme`/`fv_scheme_overrides`/`fv_solution_overrides` (uncataloged
`fvSchemes`/`fvSolution` documents) stay direct writes.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import manufactured_eikonal_ecg as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import digests, write_physics_properties

_RELPATHS = ("constant/electroProperties", "constant/physicsProperties", "system/blockMeshDict.1D")

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver eikonalSolver;",
        "",
        "eikonalSolverCoeffs",
        "{",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "    eikonalAdvectionDiffusionApproach false;",
        "    verificationModel",
        "    {",
        "        type manufacturedEikonalVerifier;",
        "    }",
        "    ecgDomains",
        "    {",
        "        ECG",
        "        {",
        "            ecgSolver none;",
        "            verificationModel",
        "            {",
        "                enabled false;",
        "                referenceQuadratureOrder 12;",
        "                checkQuadratureOrders ();",
        "            }",
        "            electrodePositions",
        "            {",
        "                E1 (0 0 0);",
        "                E2 (0 0 0);",
        "                E3 (0 0 0);",
        "                E4 (0 0 0);",
        "                E5 (0 0 0);",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]
)

_BLOCK_MESH_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    ");\n"
)

# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`.
_DIGESTS_BEFORE = {
    "constant/electroProperties": "ecd329d7105efc1fe65ccc7b4a75db40147922a9b059850597a2ce7dd3893a29",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/blockMeshDict.1D": "3bc8f7b4af377ed1b913752470f5c3d37eb3b687b99253d93efd1ec99b891a7a",
}


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "blockMeshDict.1D").write_text(_BLOCK_MESH_TEXT)


def _case() -> CaseConfig:
    return CaseConfig(case_id="1D_40", params={"dimension": "1D", "cells": 40})


def _kwargs() -> dict:
    return dict(physics_property_overrides={"type": "electroMechanicalModel"})


class TestManufacturedEikonalEcgWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-eikonal-ecg-channel-"))
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


if __name__ == "__main__":
    unittest.main()
