"""Phase 3 Task 6, completed 2026-09-23 (the decision "a parameter asserts a
final state, not only a value"): `manufactured_monodomain_pseudo_ecg` --
**full migration** of the electroProperties portion Task 6 itself reported
as resisting. The electrode-position upserts now go through
`resolve_electro_property_ensure` (`operation="ensure"`, catalog-addressed
via the declared `dynamic_path` entry
`ecgDomains.<name>.electrodePositions.<electrode>`); the conditional
`ecgDomains` removal now goes through a `plan_dict_block` raw target
(`operation="remove"`), the same "not a `ParameterAssignment`" shape the
hex-block target and `manufactured_bath_bidomain`'s own `ecgDomains` insert
already have. The uncataloged `fvSchemes`/`fvSolution`/`controlDict` edits
still stay direct writes -- see `_plan_case`'s own docstring.

Two scenarios are characterized: `ecg_enabled=False` (the ecgDomains removal
is a no-op against a fixture that never had one -- the original, already-
passing characterization) and `ecg_enabled=True` (the electrode upserts and
the ecgDomains-scoped `set`s, against a fixture whose `ecgDomains.ECG` block
already exists -- the newly migrated path). Unlike
`manufactured_bath_bidomain`, this tutorial has no undeclared-key bug
blocking it: every override this migration touches is catalog-declared
(confirmed by running both scenarios against a real fixture, not assumed),
so both scenarios reproduce `_apply_case`'s bytes exactly, across all four
files.

**Extended 2026-09-24 (Phase 3 Task 7 follow-up): `mesh_family="tet"`.**
The tet branch's numerics-profile overlays (`monodomain_tet`: both
`system/fvSchemes` and `system/fvSolution`, replaced wholesale) were a
`shutil.copy` beside the channel commit; Task 7 reclassified them as
`RenderedFile`s (`plan_verbatim_content`), not source artifacts. They are
now `extra_targets` of the same `commit_case_overrides` call. `_apply_case`
is already a thin `_plan_case` wrapper, so an apply-vs-plan comparison
would be circular: the tet digests below were captured from the
pre-migration `_plan_case` (overlays copied directly) and are the ground
truth, and `record.committed` proves the overlays are now inside the
transaction.
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


# --- ecg_enabled=True: the newly migrated electrode-ensure/ecgDomains-set
# path. Needs a fixture whose ecgDomains.ECG block already exists -- an
# ensure only creates the *leaf* key it is given (add_if_missing), not the
# scope block around it (confirmed directly: `update_foam_entry`'s own
# add_if_missing appends within an existing scope, it does not fabricate
# one) -- so a fixture missing this block would fail for the identical
# reason on both `_apply_case` and `_plan_case`, proving nothing new. ---

_ECG_ELECTRO_TEXT = "\n".join(
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
        "    ecgDomains",
        "    {",
        "        ECG",
        "        {",
        "            ecgSolver eikonalECG;",
        "            verificationModel",
        "            {",
        "                enabled false;",
        '                dimension "1D";',
        "                anisotropic false;",
        "                referenceQuadratureOrder 1;",
        "                checkQuadratureOrders (1);",
        "            }",
        "            electrodePositions",
        "            {",
        "                E1 (0 0 0);",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ]
)

# Captured 2026-09-23 against HEAD (this commit's own `_apply_case`,
# unmodified), ecg_enabled=True: full byte-for-byte match against
# `_plan_case` on all four files, confirmed by running both, not assumed --
# see this module's own docstring.
_ECG_DIGESTS_BEFORE = {
    "constant/electroProperties": "e616ab086d3fcd78528c53dddb8fcbb7928198cee5e442cde6f4640cf1ac7288",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "559dfadfa7f0d32927c9d8bd2faa9e6433a91bb37b92fd41f52b6898493b6a7b",
    "system/blockMeshDict.1D": "3bc8f7b4af377ed1b913752470f5c3d37eb3b687b99253d93efd1ec99b891a7a",
}


def _write_ecg_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ECG_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "controlDict").write_text(_CONTROL_DICT_TEXT)
    (root / "system" / "blockMeshDict.1D").write_text(_BLOCK_MESH_TEXT)


def _ecg_kwargs() -> dict:
    return dict(
        end_time=0.05, physics_property_overrides={"type": "electroMechanicalModel"},
        ecg_enabled=True,
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

    def test_characterization_apply_case_current_bytes_with_ecg_enabled(self) -> None:
        root = self.tmp / "apply_ecg"
        _write_ecg_case(root)
        tut._apply_case(root, _case(), **_ecg_kwargs())
        self.assertEqual(_digests(root), _ECG_DIGESTS_BEFORE)

    def test_plan_case_reproduces_apply_case_bytes_exactly_with_ecg_enabled(self) -> None:
        apply_root = self.tmp / "apply_ecg2"
        plan_root = self.tmp / "plan_ecg"
        _write_ecg_case(apply_root)
        _write_ecg_case(plan_root)

        tut._apply_case(apply_root, _case(), **_ecg_kwargs())
        record = tut._plan_case(plan_root, _case(), **_ecg_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        self.assertEqual(_digests(plan_root), _digests(apply_root))
        # Digest equality alone does not distinguish "went through the
        # channel" from "the old direct writer happened to produce the same
        # bytes" (both did, pre-migration, for this exact scenario -- checked
        # by reverting this tutorial's source and rerunning this file: all
        # four tests still passed, since the pre-migration direct writer was
        # already byte-correct, just unrecorded). `record.committed` is what
        # actually proves the electrode/ecgDomains writes are now part of
        # the auditable transaction, not a side effect outside it.
        committed_paths = {entry["path"] for entry in record.committed}
        self.assertIn("constant/electroProperties", committed_paths)



# --- mesh_family="tet" (2026-09-24) -----------------------------------------

_TET_DIR = Path("setup/studies/tetConvergence")

_TET_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/fvSchemes",
    "system/fvSolution",
    str(_TET_DIR / "box.geo"),
)

_PHI_BLOCK = '"phiE|phiEFinal|phiI|phiIFinal"'

_FV_SCHEMES_TEXT = (
    "FoamFile\n{\n    object fvSchemes;\n}\n"
    "gradSchemes\n{\n    default Gauss linear;\n}\n"
)

_FV_SOLUTION_TEXT = (
    "FoamFile\n{\n    object fvSolution;\n}\n"
    f"solvers\n{{\n    {_PHI_BLOCK}\n    {{\n        solver PCG;\n        tolerance 1e-06;\n    }}\n}}\n"
)

# Both overlays differ structurally from the hex documents they replace, so
# a digest can tell "overlaid" from "patched".
_TET_FV_SCHEMES_OVERLAY_TEXT = (
    "FoamFile\n{\n    object fvSchemes;\n}\n"
    "gradSchemes\n{\n    default leastSquares;\n}\n"
    "laplacianSchemes\n{\n    default Gauss linear corrected;\n}\n"
)

_TET_FV_SOLUTION_OVERLAY_TEXT = (
    "FoamFile\n{\n    object fvSolution;\n}\n"
    f"solvers\n{{\n    {_PHI_BLOCK}\n    {{\n        solver GAMG;\n        smoother GaussSeidel;\n"
    "        tolerance 1e-09;\n    }\n}\n"
)

# Captured 2026-09-24 against HEAD 6bfe26e, from the pre-migration
# `_plan_case` (both overlays installed by `shutil.copy` before the channel
# commit; `phi_tolerance` a direct `update_foam_entry` after it).
_TET_DIGESTS_BEFORE = {
    "constant/electroProperties": "51156e48d5c2a25bf96103f17a28284ff6c4dc659db935a371eb2543ebccfd29",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "559dfadfa7f0d32927c9d8bd2faa9e6433a91bb37b92fd41f52b6898493b6a7b",
    "system/fvSchemes": "8f89c17989b8a9998575fed84e4cdd706539f0bcbe726aaedc4b5b5de131b5da",
    "system/fvSolution": "63f7d9877fde8deccab4bc8889d4c6fb2610d22e608ef6539d3765bab857878a",
    str(_TET_DIR / "box.geo"): "1fdac6262213ffd774b19ed4644cc37e25d0ceda7c14bc82269222833b518948",
}


def _tet_digests(root: Path) -> dict:
    import hashlib
    return {r: hashlib.sha256((root / r).read_bytes()).hexdigest() for r in _TET_RELPATHS}


def _write_tet_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "controlDict").write_text(_CONTROL_DICT_TEXT)
    (root / "system" / "fvSchemes").write_text(_FV_SCHEMES_TEXT)
    (root / "system" / "fvSolution").write_text(_FV_SOLUTION_TEXT)
    # No blockMeshDict.3D at all: a tet case must never try to touch it.
    (root / _TET_DIR).mkdir(parents=True, exist_ok=True)
    (root / _TET_DIR / "box.geo.template").write_text(
        "lc = __LC__;\nBox(1) = {0, 0, 0, 1, 1, 1};\n"
    )
    (root / _TET_DIR / "fvSchemes").write_text(_TET_FV_SCHEMES_OVERLAY_TEXT)
    (root / _TET_DIR / "fvSolution").write_text(_TET_FV_SOLUTION_OVERLAY_TEXT)


def _tet_case() -> CaseConfig:
    return CaseConfig(
        case_id="3D_10_implicit", params={"dimension": "3D", "solver": "implicit", "cells": 10, "dt": 0.002},
    )


def _tet_kwargs() -> dict:
    return dict(
        mesh_family="tet",
        numerics_profile="monodomain_tet",
        # A direct edit to a document the overlay replaced: it must land on
        # the overlay's text, after the commit that installs it.
        phi_tolerance=1e-12,
        end_time=0.05,
        physics_property_overrides={"type": "electroMechanicalModel"},
        ecg_enabled=False,
    )


class TestManufacturedMonodomainPseudoEcgTetWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-pseudo-ecg-tet-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_tet_current_bytes(self) -> None:
        root = self.tmp / "tet"
        _write_tet_case(root)
        tut._plan_case(root, _tet_case(), **_tet_kwargs())
        self.assertEqual(_tet_digests(root), _TET_DIGESTS_BEFORE)

    def test_tet_plan_case_commits_both_overlays_through_the_channel(self) -> None:
        root = self.tmp / "tet_record"
        _write_tet_case(root)

        record = tut._plan_case(root, _tet_case(), **_tet_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        committed = {entry["path"] for entry in record.committed}
        self.assertIn("system/fvSchemes", committed)
        self.assertIn("system/fvSolution", committed)
        self.assertFalse((root / "system" / "blockMeshDict.3D").exists())
        fv_solution = (root / "system" / "fvSolution").read_text()
        self.assertIn("GAMG", fv_solution)
        self.assertNotIn("1e-09", fv_solution)


if __name__ == "__main__":
    unittest.main()
