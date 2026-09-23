"""Phase 3 Task 6: `restitution_curves` follows the `single_cell` template --
entry overrides plus `endTime`, no block mesh.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import restitution_curves as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import digests, write_control_dict, write_physics_properties

_RELPATHS = ("constant/electroProperties", "constant/physicsProperties", "system/controlDict")

# `restitution_curves` addresses `singleCellSolverCoeffs`, not the
# `monodomainSolverCoeffs`/`eikonalSolverCoeffs` blocks
# `write_channel_test_support.ELECTRO_TEXT` carries -- a local fixture,
# not a shared one, so this scope's shape stays this test's own concern.
_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver singleCellSolver;",
        "",
        "singleCellSolverCoeffs",
        "{",
        "    ionicModel BuenoOrovio;",
        "    tissue myocyte;",
        "    writeAfterTime 0;",
        "    singleCellStimulus",
        "    {",
        "        stim_amplitude 0.4;",
        "        stim_period_S1 1000;",
        "        nstim1 1;",
        "        stim_period_S2 1000;",
        "        nstim2 1;",
        "    }",
        "}",
        "",
    ]
)

# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`.
_DIGESTS_BEFORE = {
    "constant/electroProperties": "86c9443373d9c2a4eb332c73844e7592b306cfa70e0a825c9c5b9916839b7604",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "a1e22726f44d454003bbfde63ea4916e573df9699bd19689baf436c06eab3478",
}


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    write_control_dict(root)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="TNNP_myocyte_S2_350",
        params={"ionicModel": "TNNP", "tissue": "myocyte", "s2Interval": 350},
    )


def _kwargs() -> dict:
    return dict(
        stimulus_map={"TNNP": 0.55},
        s1_interval_ms=1000,
        n_s1=3,
        n_s2=1,
        write_after_time_s=2.0,
        end_time_buffer_s=0.5,
        electro_property_overrides={"singleCellSolverCoeffs.singleCellStimulus.nstim2": 2},
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestRestitutionCurvesWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-restitution-channel-"))
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
