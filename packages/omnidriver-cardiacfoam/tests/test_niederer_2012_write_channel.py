"""Phase 3 Task 6: `niederer_2012`'s hex-family path -- entry overrides,
`deltaT`/`endTime` (the latter previously written by a bespoke hand-rolled
line rewriter, `_update_end_time`, now proven byte-identical through
`plan_end_time`), and a block-mesh rewrite.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import niederer_2012 as tut
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
    "constant/electroProperties": "57dd03a0ff3a87e917cc451cc4d1a068654231e2999075281ef1ecf54306566c",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "eb97848f10cdd19576e76b61548b24c393acc4a96a856b23a51609f56a62a9da",
    "system/blockMeshDict": "e11273cdb54a7a44e20be811714e37982b622bbf6fde611da5ad52b26d93a214",
}


def _write_case(root: Path) -> None:
    write_electro_properties(root)
    write_physics_properties(root)
    write_control_dict(root)
    write_block_mesh_dict(root)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="implicit_Stewart_myocyte_DT0.005_DX0.2",
        params={
            "dx_mm": 0.2, "dt_ms": 0.005, "tissue": "myocyte",
            "ionicModel": "Stewart", "solver": "implicit",
        },
    )


def _kwargs() -> dict:
    return dict(
        electro_property_overrides={"monodomainSolverCoeffs.solutionAlgorithm": "implicitEuler"},
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestNiederer2012WriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-niederer-channel-"))
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

    def test_apply_case_with_mesh_family_tet_renders_geo_and_skips_block_mesh(self) -> None:
        """`_apply_case`'s `mesh_family == "tet"` branch has no `_plan_case`
        counterpart to delegate to (that function's own docstring: "migrates
        the hex-family path only") -- `make_spec` only wires
        `TutorialSpec.plan_case` when `mesh_family == "hex"`, so
        `apply_case` stays this branch's only route, unchanged since before
        Task 6's write-channel migration touched this tutorial at all.
        Added 2026-09-23 (Phase 3 Commit 3): the *hex* path's collapse to a
        thin `_plan_case` wrapper was mechanical, but a first, unconditional
        attempt at it would have silently broken this branch (confirmed
        against `manufactured_eikonal_ecg`'s identical shape, which had a
        real test to catch it; niederer_2012 had none, so this test closes
        that gap rather than leaving the fix unverified).
        """
        root = self.tmp / "apply_tet"
        write_electro_properties(root)
        write_physics_properties(root)
        write_control_dict(root)
        # No blockMeshDict at all: a tet call must never try to touch it.
        template_dir = root / "setup" / "studies" / "tetConvergence"
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "slab.geo.template").write_text(
            "lc = __LC__;\nBox(1) = {0, 0, 0, 1, 1, 1};\n"
        )

        tut._apply_case(
            root, _case(), mesh_family="tet",
            tet_geo_template_relpath=Path("setup/studies/tetConvergence/slab.geo.template"),
        )

        geo_text = (template_dir / "slab.geo").read_text()
        self.assertIn("lc = 0.0002;", geo_text)  # dx_mm=0.2 -> 0.2e-3 m
        self.assertFalse((root / "system" / "blockMeshDict").exists())
        electro_text = (root / "constant" / "electroProperties").read_text()
        self.assertIn("myocyte", electro_text)
        self.assertIn("implicit", electro_text)


if __name__ == "__main__":
    unittest.main()
