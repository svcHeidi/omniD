"""Phase 3 Task 6: `cable_1d_cv_convergence` follows the `single_cell`
template -- entry overrides, `deltaT`/`endTime`, and a block-mesh rewrite,
all folded into one `commit_case_overrides` transaction.

Characterizes `_apply_case`'s exact output bytes (electroProperties,
physicsProperties, controlDict, blockMeshDict), then proves `_plan_case`
reproduces them exactly.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import cable_1d_cv_convergence as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import (
    digests,
    write_block_mesh_dict,
    write_control_dict,
    write_electro_properties,
    write_physics_properties,
)

_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/blockMeshDict",
)

# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`.
_DIGESTS_BEFORE = {
    "constant/electroProperties": "b4a3142966305678bf7b3e500ab1b34e9b8bd8157c54aef7e17fbe336db0122c",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "26b9f589db66fc909924c0badb5a2ab4bff2440dbf00a2e7c8db003a6ccd760c",
    "system/blockMeshDict": "3bc8f7b4af377ed1b913752470f5c3d37eb3b687b99253d93efd1ec99b891a7a",
}


def _write_case(root: Path) -> None:
    write_electro_properties(root)
    write_physics_properties(root)
    write_control_dict(root)
    write_block_mesh_dict(root)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="implicit_Stewart_myocyte_DT0.01_DX0.5_COND01",
        params={
            "ionicModel": "Stewart", "tissue": "myocyte", "dt_ms": 0.01,
            "dx_mm": 0.5, "solver": "implicit",
            "conductivity": "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.1334 0 0.1334)",
            "conductivity_id": 1,
        },
    )


def _kwargs() -> dict:
    return dict(
        electro_property_overrides={"monodomainSolverCoeffs.solutionAlgorithm": "implicitEuler"},
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestCable1dCvConvergenceWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-cable-cv-channel-"))
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
        for relpath in _RELPATHS:
            self.assertEqual(
                (plan_root / relpath).read_bytes(), (apply_root / relpath).read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
