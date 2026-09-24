"""Phase 3 Task 6: `manufactured_eikonal_ecg`'s hex-family path -- entry
overrides (including the dynamic `ecgDomains.ECG.electrodePositions.<name>`
path) and a block-mesh rewrite move onto the channel. The optional
`grad_scheme`/`fv_scheme_overrides`/`fv_solution_overrides` (uncataloged
`fvSchemes`/`fvSolution` documents) stay direct writes.

**Extended 2026-09-24 (Phase 3 Task 7 follow-up): `mesh_family="tet"`.**
`_plan_case` was hex-only until then -- `make_spec` wired `plan_case` only
for hex, so a tet case reached `commit_case_write` not at all: `_apply_case`
kept an independent direct-write implementation for it, including a
`shutil.copy` of the `eikonal_tet` numerics overlay over `system/fvSolution`.
Task 7 reclassified that copy as a `RenderedFile`
(`plan_verbatim_content`), not a source artifact; the tet tests below pin
the pre-migration bytes (captured from that independent `_apply_case`
before it was collapsed) and prove `_plan_case`'s new tet branch reproduces
them through the channel.
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



# --- mesh_family="tet" (2026-09-24) -----------------------------------------

_TET_DIR = Path("setup/studies/tetConvergence")

_TET_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/fvSchemes",
    "system/fvSolution",
    str(_TET_DIR / "box.geo"),
)

_FV_SCHEMES_TEXT = (
    "FoamFile\n{\n    object fvSchemes;\n}\n"
    "gradSchemes\n{\n    default Gauss linear;\n}\n"
)

_FV_SOLUTION_TEXT = (
    "FoamFile\n{\n    object fvSolution;\n}\n"
    "solvers\n{\n    Vm\n    {\n        solver PCG;\n        tolerance 1e-06;\n    }\n}\n"
)

# Structurally different from the hex fvSolution above (a different solver
# block, an extra key), so a digest can tell "overlaid" from "patched".
_TET_FV_SOLUTION_OVERLAY_TEXT = (
    "FoamFile\n{\n    object fvSolution;\n}\n"
    "solvers\n{\n    Vm\n    {\n        solver GAMG;\n        smoother GaussSeidel;\n"
    "        tolerance 1e-09;\n    }\n}\n"
)

# Captured 2026-09-24 against HEAD 6bfe26e, from the pre-migration
# `_apply_case`'s independent tet implementation (`render_tet_geo`, the
# overlay `shutil.copy`, `grad_scheme`/`fv_solution_overrides` via
# `update_foam_entry`, then `apply_electro_property_overrides`/
# `apply_physics_property_overrides`), before any of it was routed through
# `_plan_case`.
_TET_DIGESTS_BEFORE = {
    "constant/electroProperties": "8cb14860eedca1f886a1593da5b237c44885795321f9785bc052d61fd46d3003",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/fvSchemes": "4ad8d4bb3235c55ea8aa7e3f665e03c3161835e74c7e68cd69129beebddd874b",
    "system/fvSolution": "579204b80eb8098d87bb6390faa52efc7c6c52f571c072664be76c92d0d675fa",
    str(_TET_DIR / "box.geo"): "1fdac6262213ffd774b19ed4644cc37e25d0ceda7c14bc82269222833b518948",
}


def _write_tet_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "fvSchemes").write_text(_FV_SCHEMES_TEXT)
    (root / "system" / "fvSolution").write_text(_FV_SOLUTION_TEXT)
    # No blockMeshDict.3D at all: a tet case must never try to touch it.
    (root / _TET_DIR).mkdir(parents=True, exist_ok=True)
    (root / _TET_DIR / "box.geo.template").write_text(
        "lc = __LC__;\nBox(1) = {0, 0, 0, 1, 1, 1};\n"
    )
    (root / _TET_DIR / "fvSolution").write_text(_TET_FV_SOLUTION_OVERLAY_TEXT)


def _tet_case() -> CaseConfig:
    return CaseConfig(case_id="3D_10", params={"dimension": "3D", "cells": 10})


def _tet_kwargs() -> dict:
    return dict(
        mesh_family="tet",
        numerics_profile="eikonal_tet",
        grad_scheme="least_squares",
        # Targets a key only the *overlay* has in this block's final form --
        # see `test_tet_fv_solution_override_lands_on_the_overlay` below.
        fv_solution_overrides=[{"key": "tolerance", "value": 1e-12, "scope": ["solvers", "Vm"]}],
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestManufacturedEikonalEcgTetWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-eikonal-ecg-tet-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_tet_apply_case_current_bytes(self) -> None:
        root = self.tmp / "apply_tet"
        _write_tet_case(root)
        tut._apply_case(root, _tet_case(), **_tet_kwargs())
        self.assertEqual(digests(root, *_TET_RELPATHS), _TET_DIGESTS_BEFORE)

    def test_tet_plan_case_commits_the_overlay_through_the_channel(self) -> None:
        root = self.tmp / "plan_tet"
        _write_tet_case(root)

        record = tut._plan_case(root, _tet_case(), **_tet_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        committed = {entry["path"] for entry in record.committed}
        self.assertIn("system/fvSolution", committed)
        self.assertIn("constant/electroProperties", committed)
        self.assertEqual(digests(root, *_TET_RELPATHS), _TET_DIGESTS_BEFORE)
        self.assertFalse((root / "system" / "blockMeshDict.3D").exists())

    def test_tet_fv_solution_override_lands_on_the_overlay(self) -> None:
        """Ordering, not just content: `fv_solution_overrides` is a direct
        `update_foam_entry` on `system/fvSolution`, and the overlay replaces
        that same document wholesale. `_plan_case` ran its direct `fvSchemes`/
        `fvSolution` edits *before* its channel commit when it was hex-only
        (harmless then: disjoint documents); once the overlay is itself a
        channel target, an edit made before the commit is silently
        overwritten by it. The override must land on the overlay's text."""
        root = self.tmp / "plan_tet_order"
        _write_tet_case(root)

        tut._plan_case(root, _tet_case(), **_tet_kwargs())

        fv_solution = (root / "system" / "fvSolution").read_text()
        self.assertIn("GAMG", fv_solution)
        self.assertNotIn("1e-09", fv_solution)
        self.assertNotIn("PCG", fv_solution)


if __name__ == "__main__":
    unittest.main()
