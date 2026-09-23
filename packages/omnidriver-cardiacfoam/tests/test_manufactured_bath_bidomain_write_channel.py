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
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
