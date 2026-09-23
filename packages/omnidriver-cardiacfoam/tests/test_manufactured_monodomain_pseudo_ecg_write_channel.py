"""Phase 3 Task 6: `manufactured_monodomain_pseudo_ecg` -- **partial
migration**. Only `deltaT`/`endTime` and the hex-family block-mesh rewrite
move onto the channel; the electroProperties edits (an add-if-missing
electrode upsert, a conditional `ecgDomains` removal) and the uncataloged
`fvSchemes`/`fvSolution`/`controlDict` edits stay direct writes -- see
`_plan_case`'s own docstring for why they resist the
clone_and_patch/ParameterAssignment contract.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import manufactured_monodomain_pseudo_ecg as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import write_physics_properties

_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/blockMeshDict.1D",
)

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver monodomainSolver;",
        "",
        "monodomainSolverCoeffs",
        "{",
        '    dimension "1D";',
        "    solutionAlgorithm implicit;",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "    verificationModel",
        "    {",
        "        type manufacturedMonodomainVerifier;",
        "    }",
        "}",
        "",
    ]
)

_CONTROL_DICT_TEXT = "\n".join(
    ["FoamFile", "{", "    object controlDict;", "}", "", "deltaT          1e-06;", "endTime         1;", ""],
)

_BLOCK_MESH_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    ");\n"
)


def _digests(root: Path) -> dict:
    import hashlib
    return {r: hashlib.sha256((root / r).read_bytes()).hexdigest() for r in _RELPATHS}


# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`
# (ecg_enabled left at its default False, so no electrode/ecgDomains writes
# fire -- this test exercises the migrated subset; the resisting subset is
# unchanged and untested here since it is unchanged code).
_DIGESTS_BEFORE = {
    "constant/electroProperties": "89881a4852694c7d58797ba541f993a64a802f445aacf9d0f698b81183f2466f",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "559dfadfa7f0d32927c9d8bd2faa9e6433a91bb37b92fd41f52b6898493b6a7b",
    "system/blockMeshDict.1D": "3bc8f7b4af377ed1b913752470f5c3d37eb3b687b99253d93efd1ec99b891a7a",
}


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "controlDict").write_text(_CONTROL_DICT_TEXT)
    (root / "system" / "blockMeshDict.1D").write_text(_BLOCK_MESH_TEXT)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="1D_40_implicit", params={"dimension": "1D", "solver": "implicit", "cells": 40, "dt": 0.002},
    )


def _kwargs() -> dict:
    return dict(
        end_time=0.05, physics_property_overrides={"type": "electroMechanicalModel"},
        ecg_enabled=False,
    )


class TestManufacturedMonodomainPseudoEcgWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-pseudo-ecg-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_apply_case_current_bytes(self) -> None:
        root = self.tmp / "apply"
        _write_case(root)
        tut._apply_case(root, _case(), **_kwargs())
        self.assertEqual(_digests(root), _DIGESTS_BEFORE)

    def test_plan_case_reproduces_apply_case_bytes_exactly(self) -> None:
        apply_root = self.tmp / "apply2"
        plan_root = self.tmp / "plan"
        _write_case(apply_root)
        _write_case(plan_root)

        tut._apply_case(apply_root, _case(), **_kwargs())
        record = tut._plan_case(plan_root, _case(), **_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        self.assertEqual(_digests(plan_root), _digests(apply_root))


if __name__ == "__main__":
    unittest.main()
