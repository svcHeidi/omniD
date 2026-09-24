"""Phase 3 Task 6's completion (2026-09-23 decision, "a parameter asserts a
final state, not only a value"): `manufactured_bath_bidomain` **in full**.

Task 6 itself reported this tutorial as resisting the
`clone_and_patch`/`ParameterAssignment` contract outright: its
`fdaBathVariant` switch removes a stale bath-boundary patch entry left
behind by a previous case sharing this reused `case_root`, interleaved with
two upserts and two `apply_electro_property_overrides` calls, and
`ParameterAssignment` had no vocabulary for a removal or an upsert. It does
now (`operation="ensure"`/`"remove"`), plus a `plan_dict_block` raw target
for the whole-`ecgDomains`-block insert/removal, which is not a
`ParameterAssignment` at all (see `_plan_case`'s own docstring).

**A second, previously undocumented production bug, found while writing
this test, out of this task's mandate to fix** -- the same class of defect
`manufactured_monodomain_total_lagrangian_em` has for a different key
(Task 6's own report): `case_overrides` unconditionally includes
`f"{electro_properties_scope}.manufacturedBidomain.fdaBathVariant"`, a key
`dict_entries_catalog.py` does not declare anywhere (confirmed by grep, not
assumed -- that module's own 2026-09-19 correction note explains why:
"native reads that block only at electroProperties top level, for ECG
inheritance, never under `<solver>Coeffs`" -- removed from the catalog that
day; this tutorial's write of it was never updated to match). Since this key
is unconditional -- not gated behind any parameter -- **`_apply_case` raises
`ValueError` for every call, with no way to avoid it**, confirmed by running
it with the tutorial's own default arguments against a real fixture. This
means true byte-for-byte parity against `_apply_case` is not achievable for
this tutorial's `constant/electroProperties` output (nothing `_apply_case`
writes there past the raise can be a ground truth, because it never gets
there): `_apply_case`'s own `case_overrides` call fails immediately, atomically
-- `resolve_entry_overrides` raises mid-iteration before returning anything,
so *none* of that dict's keys are written, including the ones the catalog
does declare (`dimension`, `solutionAlgorithm`, `verificationModel.type`,
...). `_plan_case` classifies the dead key separately (`uncataloged_case_overrides`,
written last, directly, matching the established "uncataloged key stays
direct" pattern every other migrated tutorial already uses for a key the
catalog does not declare) rather than bundling it with the catalog-valid
keys the way `_apply_case` does -- so `_plan_case`'s channel commit succeeds
in full before it too fails on the same dead key. The two are proven
identical exactly as far as that is meaningful: the same exception, and
byte-for-byte identical `system/controlDict`/`system/blockMeshDict.2D`
(both fully migrated and untouched by this bug). `constant/electroProperties`
is instead characterized directly, against expected values, not against
`_apply_case`'s broken output.

**Extended 2026-09-24 (Phase 3 Task 7 follow-up): `mesh_family="tet"`.**
The tet branch's `bath_bidomain_tet` numerics overlay (a wholesale
replacement of `system/fvSchemes`) was a `shutil.copy` beside the channel
commit; Task 7 reclassified it as a `RenderedFile` (`plan_verbatim_content`),
not a source artifact, and it is now an `extra_targets` entry of the same
`commit_case_overrides` call. The dead-key raise above still ends every
call, so `_plan_case` never returns its record: the tet test captures it by
wrapping `commit_case_overrides`, which has already returned by the time the
direct dead-key write raises.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from omnidriver.cardiacfoam.tutorials import manufactured_bath_bidomain as tut
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import write_physics_properties

_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/blockMeshDict.2D",
)

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver bidomainSolver;",
        "",
        "bidomainSolverCoeffs",
        "{",
        '    dimension "1D";',
        "    solutionAlgorithm explicit;",
        "    bathPredictorCorrector false;",
        "    verificationModel",
        "    {",
        "        type manufacturedFDAMonodomainVerifier;",
        "        fdaBathVariant groundElectrode;",
        "    }",
        "    manufacturedBidomain",
        "    {",
        "        fdaBathVariant groundElectrode;",
        "    }",
        "    bathPotentialDomain",
        "    {",
        "        phiERefPoint (0 0 0);",
        "        phiEReferenceValue 0;",
        "        groundPatches",
        "        {",
        "            xMin 0;",
        "        }",
        "        surfaceCurrentPatches",
        "        {",
        "        }",
        "    }",
        "}",
        "",
    ]
)

# writeInterval is present (unlike write_channel_test_support.write_control_dict's
# fixture): this tutorial's own controlDict edit is a strict `update_foam_entry`
# with no `add_if_missing`, same as `endTime` -- the key must already exist.
_CONTROL_DICT_TEXT = "\n".join(
    ["FoamFile", "{", "    object controlDict;", "}", "",
     "deltaT          1e-06;", "endTime         1;", "writeInterval   1;", ""],
)

_BLOCK_MESH_2D_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 5 4 8 9 13 12) (10 10 10) simpleGrading (1 1 1)\n"
    "    hex (1 2 6 5 9 10 14 13) (10 10 10) simpleGrading (1 1 1)\n"
    "    hex (2 3 7 6 10 11 15 14) (10 10 10) simpleGrading (1 1 1)\n"
    ");\n"
)

_DEAD_KEY_MESSAGE_FRAGMENT = (
    "bidomainSolverCoeffs.manufacturedBidomain.fdaBathVariant"
)


def _digests(root: Path) -> dict:
    import hashlib
    return {r: hashlib.sha256((root / r).read_bytes()).hexdigest() for r in _RELPATHS}


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "controlDict").write_text(_CONTROL_DICT_TEXT)
    (root / "system" / "blockMeshDict.2D").write_text(_BLOCK_MESH_2D_TEXT)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="2D_20_implicit", params={"dimension": "2D", "solver": "implicit", "cells": 20, "dt": 0.001},
    )


# Captured 2026-09-23 against HEAD 26f2090, from the unmodified `_apply_case`
# -- the default call: fda_bath_variant="electrodePair" (removes the
# fixture's leftover groundPatches.xMin, upserts surfaceCurrentPatches.xMin/
# xMax), ecg_enabled=False (ecgDomains removal is a no-op -- the fixture
# never had one). Raises on the dead key before ever reaching case_overrides'
# valid entries or the two calls after it (ecgDomains removal,
# electro_property_overrides, physics_property_overrides) -- see module
# docstring.
_ELECTRODE_PAIR_KWARGS = dict(end_time=0.02, physics_property_overrides={"type": "electroMechanicalModel"})

# fda_bath_variant="groundElectrode" (ensures groundPatches.xMin again and
# surfaceCurrentPatches.xMax fresh; removes nothing new), ecg_enabled=True
# (inserts the whole ecgDomains block, then sets three keys inside it --
# the load-bearing dict-then-value order this migration depends on).
_GROUND_ELECTRODE_ECG_KWARGS = dict(
    end_time=0.02, fda_bath_variant="groundElectrode", ecg_enabled=True,
)


class TestManufacturedBathBidomainWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-bath-bidomain-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # **Corrected 2026-09-23 (Commit 3, same task):** this class used to carry
    # two tests here characterizing `_apply_case` raising after a *partial*,
    # independent set of writes (`_ELECTRODE_PAIR_APPLY_DIGESTS`/
    # `_GROUND_ELECTRODE_ECG_APPLY_DIGESTS`, captured before Commit 3
    # collapsed `_apply_case` to a thin wrapper over `_plan_case`). Once
    # `_apply_case` *is* `_plan_case`, those digests are simply
    # `_plan_case`'s own -- proven by running this file against the collapsed
    # source, which failed exactly those two tests with `_apply_case`'s
    # digest now equal to `_plan_case`'s. Removed rather than updated to
    # assert a now-tautological "`_apply_case` matches `_apply_case`"; the
    # dead-key raise is still characterized below, where it is meaningful
    # (`_plan_case` raising it, `_apply_case` -- now the same code --
    # matching).

    # --- _plan_case raises the identical error, and matches _apply_case
    # byte-for-byte on every document the dead key's bug does not corrupt
    # (trivially so post-collapse -- see the note above -- but this also
    # still stands as the direct characterization of what `_apply_case`,
    # i.e. `_plan_case`, actually does). ---

    def test_electrode_pair_plan_case_raises_identically_and_matches_where_comparable(self) -> None:
        apply_root = self.tmp / "apply_ep2"
        plan_root = self.tmp / "plan_ep"
        _write_case(apply_root)
        _write_case(plan_root)

        with self.assertRaises(ValueError) as apply_exc:
            tut._apply_case(apply_root, _case(), **_ELECTRODE_PAIR_KWARGS)
        with self.assertRaises(ValueError) as plan_exc:
            tut._plan_case(plan_root, _case(), **_ELECTRODE_PAIR_KWARGS)
        self.assertEqual(str(apply_exc.exception), str(plan_exc.exception))

        apply_digests = _digests(apply_root)
        plan_digests = _digests(plan_root)
        # Untouched by the dead-key bug in either path -- true byte parity.
        self.assertEqual(
            plan_digests["system/controlDict"], apply_digests["system/controlDict"],
        )
        self.assertEqual(
            plan_digests["system/blockMeshDict.2D"], apply_digests["system/blockMeshDict.2D"],
        )

    def test_electrode_pair_plan_case_electro_properties_is_correct(self) -> None:
        """Not comparable to `_apply_case` (see module docstring) --
        characterized directly instead. The channel commit succeeds in full
        before the separate, direct dead-key write raises, so every
        catalog-valid override this tutorial makes actually lands."""
        root = self.tmp / "plan_ep_direct"
        _write_case(root)
        with self.assertRaises(ValueError):
            tut._plan_case(root, _case(), **_ELECTRODE_PAIR_KWARGS)

        content = (root / "constant" / "electroProperties").read_text()
        self.assertIn('dimension    "2D"', content)
        self.assertIn("solutionAlgorithm    implicit", content)
        self.assertIn("type    manufacturedFDABathBidomainVerifier", content)
        self.assertIn("fdaBathVariant    electrodePair", content)
        self.assertIn("phiERefPoint    (-0.9 0.525 0.025)", content)
        self.assertIn("phiEReferenceValue    0.0", content)
        self.assertIn("xMin    -0.01", content)
        self.assertIn("xMax    0.01", content)
        # The stale groundPatches.xMin is genuinely gone, not just untouched
        # -- the removal this tutorial could not previously express.
        self.assertNotIn("groundPatches\n        {\n            xMin", content)

        physics_content = (root / "constant" / "physicsProperties").read_text()
        self.assertIn("electroMechanicalModel", physics_content)

    def test_ground_electrode_with_ecg_plan_case_raises_identically_and_matches_where_comparable(self) -> None:
        apply_root = self.tmp / "apply_ge2"
        plan_root = self.tmp / "plan_ge"
        _write_case(apply_root)
        _write_case(plan_root)

        with self.assertRaises(ValueError) as apply_exc:
            tut._apply_case(apply_root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)
        with self.assertRaises(ValueError) as plan_exc:
            tut._plan_case(plan_root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)
        self.assertEqual(str(apply_exc.exception), str(plan_exc.exception))

        apply_digests = _digests(apply_root)
        plan_digests = _digests(plan_root)
        self.assertEqual(
            plan_digests["system/controlDict"], apply_digests["system/controlDict"],
        )
        self.assertEqual(
            plan_digests["system/blockMeshDict.2D"], apply_digests["system/blockMeshDict.2D"],
        )

    def test_ground_electrode_with_ecg_plan_case_electro_properties_is_correct(self) -> None:
        root = self.tmp / "plan_ge_direct"
        _write_case(root)
        with self.assertRaises(ValueError):
            tut._plan_case(root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)

        content = (root / "constant" / "electroProperties").read_text()
        self.assertIn("fdaBathVariant    groundElectrode", content)
        self.assertIn("xMin    0.0", content)
        self.assertIn("xMax    0.01", content)
        # The ecgDomains block exists, and the case-specific overrides landed
        # inside it -- proof the block-then-patch order actually held (also
        # exercised directly, with a differing value, in
        # test_case_rendering_operations.py).
        self.assertIn("ecgDomains", content)
        self.assertIn("torsoECG", content)
        self.assertIn("bathECGManufacturedVerifier", content)
        self.assertIn("pseudoECG", content)



# --- mesh_family="tet" (2026-09-24) -----------------------------------------

_TET_DIR = Path("setup/studies/tetConvergence")

_TET_RELPATHS = (
    "constant/electroProperties",
    "constant/physicsProperties",
    "system/controlDict",
    "system/fvSchemes",
    str(_TET_DIR / "three_domain_box.geo"),
)

_FV_SCHEMES_TEXT = (
    "FoamFile\n{\n    object fvSchemes;\n}\n"
    "gradSchemes\n{\n    default Gauss linear;\n}\n"
)

# Structurally different from the hex fvSchemes it replaces, so a digest can
# tell "overlaid" from "patched".
_TET_FV_SCHEMES_OVERLAY_TEXT = (
    "FoamFile\n{\n    object fvSchemes;\n}\n"
    "gradSchemes\n{\n    default leastSquares;\n}\n"
    "laplacianSchemes\n{\n    default Gauss linear corrected;\n}\n"
)

# Captured 2026-09-24 against HEAD 6bfe26e, from the pre-migration
# `_plan_case` (overlay installed by `shutil.copy` before the channel commit;
# `grad_scheme` a direct `update_foam_entry` after it; then the dead-key
# raise).
_TET_DIGESTS_BEFORE = {
    "constant/electroProperties": "88e024f5596ae509e1e43ef1b9d1820e8a19f7784f6e89fca547683edc9e024f",
    "constant/physicsProperties": "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b",
    "system/controlDict": "e3aff377cbd21b809f6e7f307abe1cefc83d19f05c4fa10fefd1e6f28db94112",
    "system/fvSchemes": "9dcbd30b18e001311c8a3009d36ae4468f23d82d5005f163d97d67459ab5c062",
    str(_TET_DIR / "three_domain_box.geo"): "1fdac6262213ffd774b19ed4644cc37e25d0ceda7c14bc82269222833b518948",
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
    # No blockMeshDict.3D at all: a tet case must never try to touch it.
    (root / _TET_DIR).mkdir(parents=True, exist_ok=True)
    (root / _TET_DIR / "three_domain_box.geo.template").write_text(
        "lc = __LC__;\nBox(1) = {0, 0, 0, 1, 1, 1};\n"
    )
    (root / _TET_DIR / "fvSchemes").write_text(_TET_FV_SCHEMES_OVERLAY_TEXT)


def _tet_case() -> CaseConfig:
    return CaseConfig(
        case_id="3D_10_implicit", params={"dimension": "3D", "solver": "implicit", "cells": 10, "dt": 0.001},
    )


# A direct edit to the document the overlay replaced: it must land on the
# overlay's text, after the commit that installs it.
_TET_KWARGS = dict(
    mesh_family="tet", numerics_profile="bath_bidomain_tet", grad_scheme="gauss_linear",
    end_time=0.02, physics_property_overrides={"type": "electroMechanicalModel"},
)


class TestManufacturedBathBidomainTetWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-bath-bidomain-tet-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_tet_current_bytes(self) -> None:
        root = self.tmp / "tet"
        _write_tet_case(root)
        with self.assertRaisesRegex(ValueError, _DEAD_KEY_MESSAGE_FRAGMENT):
            tut._plan_case(root, _tet_case(), **_TET_KWARGS)
        self.assertEqual(_tet_digests(root), _TET_DIGESTS_BEFORE)

    def test_tet_plan_case_commits_the_overlay_through_the_channel(self) -> None:
        root = self.tmp / "tet_record"
        _write_tet_case(root)
        records = []
        real_commit = tut.commit_case_overrides

        def capture(*args, **kwargs):
            record = real_commit(*args, **kwargs)
            records.append(record)
            return record

        with mock.patch.object(tut, "commit_case_overrides", side_effect=capture):
            with self.assertRaisesRegex(ValueError, _DEAD_KEY_MESSAGE_FRAGMENT):
                tut._plan_case(root, _tet_case(), **_TET_KWARGS)

        self.assertEqual(len(records), 1)
        committed = {entry["path"] for entry in records[0].committed}
        self.assertIn("system/fvSchemes", committed)
        self.assertFalse((root / "system" / "blockMeshDict.3D").exists())
        fv_schemes = (root / "system" / "fvSchemes").read_text()
        self.assertIn("laplacianSchemes", fv_schemes)
        self.assertNotIn("leastSquares", fv_schemes)


if __name__ == "__main__":
    unittest.main()
