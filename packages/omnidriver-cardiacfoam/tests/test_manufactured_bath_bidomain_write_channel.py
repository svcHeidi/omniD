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

**Corrected 2026-09-23 (later same day).** This module used to characterize
a *bug*: `_plan_case` unconditionally also wrote
`bidomainSolverCoeffs.manufacturedBidomain.fdaBathVariant`, a key
`dict_entries_catalog.py` does not declare anywhere (confirmed by grep --
that module's own 2026-09-19 correction note explains why: "native reads
that block only at electroProperties top level, for ECG inheritance, never
under `<solver>Coeffs`" -- removed from the catalog that day; this
tutorial's write of it was never updated to match). Since that write was
unconditional, `_apply_case`/`_plan_case` raised `ValueError` for *every*
call, with no way to avoid it -- confirmed by running the tutorial with its
own default arguments against a real fixture, and this module used to
characterize exactly that: identical exceptions, and byte parity limited to
the two documents (`controlDict`, `blockMeshDict.2D`) the dead key's raise
never reached.

The dead write is now removed (`manufactured_bath_bidomain.py`'s own
docstring records the correction): the authoritative native tree
(`~/noFrontendCardiacFoam_minor_errors/tutorials/manufacturedSolutions/
bathBidomain/constant/electroProperties`) has no `manufacturedBidomain`
block at all, and `manufacturedFDABathBidomainVerifier.C` reads the variant
from `verificationModel.fdaBathVariant` -- exactly the catalog-declared key
(`$ELECTRO_MODEL_COEFFS.verificationModel.fdaBathVariant`) this tutorial's
`case_overrides` already wrote alongside the dead one. Removing the dead
write therefore changes nothing about which *value* reaches the solver; it
only stops the tutorial from raising before that value's write (and every
other catalog-valid write in the same batch) ever lands. This module now
characterizes the fixed behaviour directly: `_apply_case` and `_plan_case`
succeed (no raise) and produce byte-identical output on every document,
`verificationModel.fdaBathVariant` carries the requested variant (including
the non-default `groundElectrode`, exercised explicitly below), and no
`manufacturedBidomain` block is ever written.

**Regression check performed while writing this test:** reverting
`manufactured_bath_bidomain.py`'s fix (re-adding the unconditional
`manufacturedBidomain.fdaBathVariant` write) makes every test below fail --
`_apply_case`/`_plan_case` raise `ValueError` again instead of returning a
record, since `assertRaises` is no longer used here.
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

# Matches the authoritative native tree's own fixture shape
# (~/noFrontendCardiacFoam_minor_errors/tutorials/manufacturedSolutions/
# bathBidomain/constant/electroProperties): no `manufacturedBidomain` block
# -- native never reads one there, and this tutorial no longer writes one.
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


# fda_bath_variant="electrodePair" (the tutorial's own default): removes the
# fixture's leftover groundPatches.xMin, upserts surfaceCurrentPatches.xMin/
# xMax.
_ELECTRODE_PAIR_KWARGS = dict(end_time=0.02, physics_property_overrides={"type": "electroMechanicalModel"})

# fda_bath_variant="groundElectrode" (the non-default variant a caller could
# never actually get before this fix -- see manufactured_bath_bidomain.py's
# own corrected docstring): ensures groundPatches.xMin again and
# surfaceCurrentPatches.xMax fresh; removes nothing new. ecg_enabled=True
# (inserts the whole ecgDomains block, then sets three keys inside it -- the
# load-bearing dict-then-value order this migration depends on).
_GROUND_ELECTRODE_ECG_KWARGS = dict(
    end_time=0.02, fda_bath_variant="groundElectrode", ecg_enabled=True,
)


class TestManufacturedBathBidomainWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-bath-bidomain-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_electrode_pair_apply_case_and_plan_case_succeed_and_match_byte_for_byte(self) -> None:
        apply_root = self.tmp / "apply_ep"
        plan_root = self.tmp / "plan_ep"
        _write_case(apply_root)
        _write_case(plan_root)

        tut._apply_case(apply_root, _case(), **_ELECTRODE_PAIR_KWARGS)
        tut._plan_case(plan_root, _case(), **_ELECTRODE_PAIR_KWARGS)

        apply_digests = _digests(apply_root)
        plan_digests = _digests(plan_root)
        for relpath in _RELPATHS:
            self.assertEqual(
                plan_digests[relpath], apply_digests[relpath],
                f"{relpath} differs between _apply_case and _plan_case",
            )

    def test_electrode_pair_electro_properties_carries_the_default_variant_at_the_correct_scope(self) -> None:
        root = self.tmp / "plan_ep_direct"
        _write_case(root)
        tut._plan_case(root, _case(), **_ELECTRODE_PAIR_KWARGS)

        content = (root / "constant" / "electroProperties").read_text()
        self.assertIn('dimension    "2D"', content)
        self.assertIn("solutionAlgorithm    implicit", content)
        self.assertIn("type    manufacturedFDABathBidomainVerifier", content)
        # The value the native verifier actually reads
        # (verificationModel.fdaBathVariant) carries the requested variant --
        # this is the fix: it used to be shadowed by a second, dead write to
        # bidomainSolverCoeffs.manufacturedBidomain.fdaBathVariant, a key
        # nothing in the native tree ever reads (see module docstring).
        self.assertIn("fdaBathVariant    electrodePair", content)
        self.assertNotIn("manufacturedBidomain", content)
        self.assertIn("phiERefPoint    (-0.9 0.525 0.025)", content)
        self.assertIn("phiEReferenceValue    0.0", content)
        self.assertIn("xMin    -0.01", content)
        self.assertIn("xMax    0.01", content)
        # The stale groundPatches.xMin is genuinely gone, not just untouched
        # -- the removal this tutorial could not previously express.
        self.assertNotIn("groundPatches\n        {\n            xMin", content)

        physics_content = (root / "constant" / "physicsProperties").read_text()
        self.assertIn("electroMechanicalModel", physics_content)

    def test_ground_electrode_with_ecg_apply_case_and_plan_case_succeed_and_match_byte_for_byte(self) -> None:
        apply_root = self.tmp / "apply_ge"
        plan_root = self.tmp / "plan_ge"
        _write_case(apply_root)
        _write_case(plan_root)

        tut._apply_case(apply_root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)
        tut._plan_case(plan_root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)

        apply_digests = _digests(apply_root)
        plan_digests = _digests(plan_root)
        for relpath in _RELPATHS:
            self.assertEqual(
                plan_digests[relpath], apply_digests[relpath],
                f"{relpath} differs between _apply_case and _plan_case",
            )

    def test_ground_electrode_electro_properties_carries_the_non_default_variant_at_the_correct_scope(self) -> None:
        """The variant a caller requesting `groundElectrode` through this
        tutorial has never actually gotten before this fix (see
        `manufactured_bath_bidomain.py`'s corrected `_plan_case` docstring):
        the old unconditional dead write always raised before this value's
        catalog-valid write could ever reach disk."""
        root = self.tmp / "plan_ge_direct"
        _write_case(root)
        tut._plan_case(root, _case(), **_GROUND_ELECTRODE_ECG_KWARGS)

        content = (root / "constant" / "electroProperties").read_text()
        self.assertIn("fdaBathVariant    groundElectrode", content)
        self.assertNotIn("manufacturedBidomain", content)
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
