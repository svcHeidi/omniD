"""Phase 3 Task 6: `cable_1d_restitution` -- block mesh, `deltaT`/`endTime`
(computed by either of its two pacing modes -- unchanged arithmetic), and
electro/physics overrides move onto the channel. `.driverfoam_case_id` and
`.cardiacfoam_protocol.json` stay direct writes (Task 7's classification).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import cable_1d_restitution as tut
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import digests, write_control_dict, write_physics_properties

_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/blockMeshDict",
    ".driverfoam_case_id",
    ".cardiacfoam_protocol.json",
)

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver monodomainSolver;",
        "",
        "monodomainSolverCoeffs",
        "{",
        "    ionicModel Stewart;",
        "    tissue myocyte;",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "    solutionAlgorithm explicit;",
        "    externalStimulus",
        "    {",
        "        stimulusStartTimeList (0);",
        "        stimulusLocationMinList ((0 0 0));",
        "        stimulusLocationMaxList ((0 0 0));",
        "        stimulusDurationList (0);",
        "        stimulusIntensityList (0);",
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
    "constant/electroProperties": "047e2768bb0a27ca749db6478412790e8f7bcd32fc37c034dc0c8cd1bd821c0f",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "f99cbe12482ee848c271eedaec342145bb63c1cd22cfe4f3d59b354b32c8548f",
    "system/blockMeshDict": "3bc8f7b4af377ed1b913752470f5c3d37eb3b687b99253d93efd1ec99b891a7a",
    ".driverfoam_case_id": "4962a4727d540ad6f88b16cdb83bc3c7bef469c011aed967a3c89696a2aec9a2",
    ".cardiacfoam_protocol.json": "703432f3d5e8a65bcfd5ce6557807ce7459842ad9dc93f9c76bf59a81bfc5392",
}


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    write_control_dict(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "blockMeshDict").write_text(_BLOCK_MESH_TEXT)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="Stewart_myocyte_DT0.02_DX0.5_COND01_S350",
        params={
            "ionicModel": "Stewart", "tissue": "myocyte", "dt_ms": 0.02, "dx_mm": 0.5,
            "solver": "explicit", "conductivity": "[-1 -3 3 0 0 2 0] (0.1334 0 0 0.1334 0 0.1334)",
            "s2Interval": 350.0,
        },
    )


def _kwargs() -> dict:
    return dict(
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestCable1dRestitutionWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-cable-restitution-channel-"))
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
