"""Phase 3 Task 6: `manufactured_monodomain_total_lagrangian_em` -- entry
overrides on two documents (electroProperties, electroMechanicalProperties),
a block-mesh rewrite, and `deltaT`, folded into one transaction.

**Corrected 2026-09-23 (later same day).** This module used to characterize
a *bug*: the tutorial's hardcoded key,
``sequentialElectroMechanicalCoeffs.electromechanicalVerificationModel.type``,
matched nothing the native reader actually looks up.
``electromechanicalVerificationModel.C``'s ``New``/``configured`` read
``verificationModel.type`` off the ``<type>Coeffs`` subDict (confirmed
against ``~/noFrontendCardiacFoam_minor_errors/src/verificationModels/
electromechanicsVerification/electromechanicalVerificationModel.C`` and
``~/noFrontendCardiacFoam_minor_errors/src/electroMechanicalModels/
electroMechanicalModel/electroMechanicalModel.C``'s
``electroMechanicalProperties_(subDict(type + "Coeffs"))``, and directly
against the tutorial's own native fixture,
``~/noFrontendCardiacFoam_minor_errors/tutorials/manufacturedSolutions/
monodomainTotalLagrangianEM/constant/electroMechanicalProperties``, which
carries ``verificationModel { type manufacturedElectromechanicsVerifier;
... }`` -- no ``electromechanicalVerificationModel`` block at all), not
``electromechanicalVerificationModel.type``. Routing the wrong key through
``resolve_entry_overrides`` additionally validated it against the
*physicsProperties* catalog (``electro_properties_path`` was never passed
for this call, so ``is_electro=False``) -- a catalog that never declared
anything under ``sequentialElectroMechanicalCoeffs`` in the first place,
since ``electroMechanicalProperties`` is not that catalog's document
(``dict_key_allowlist.json``'s own waiver notes say so explicitly). So
``_apply_case``'s own DEFAULT call (no `electromechanical_property_overrides`
at all) always raised `ValueError`, independent of Task 6, and independent
of the key's spelling.

The fix (`manufactured_monodomain_total_lagrangian_em.py`'s own corrected
`_plan_case` docstring records it) moves this write off the catalog-checked
channel entirely -- there is no catalog claiming
`electroMechanicalProperties` to check against -- onto a direct
`update_foam_entry` call at the correct key,
`sequentialElectroMechanicalCoeffs.verificationModel.type`, run after the
channel commit succeeds. This module now characterizes the fixed behaviour
directly: `_apply_case`/`_plan_case` succeed (no raise), the two are
byte-identical on every document, and `verificationModel.type` carries the
requested verifier -- exercised with a non-default value below, since the
default was never itself the defect.

**Regression check performed while writing this test:** reverting the fix
(routing the write back through `resolve_entry_overrides` under the old,
misspelled, wrongly-scoped key) makes every test below fail --
`_apply_case`/`_plan_case` raise `ValueError` again instead of returning a
record.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.tutorials import (
    manufactured_monodomain_total_lagrangian_em as tut,
)
from omnidriver.core.runtime.models import CaseConfig
from write_channel_test_support import write_control_dict, write_physics_properties

_RELPATHS = (
    "constant/electroMechanicalProperties",
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
        "    conductivity [-1 -3 3 0 0 2 0] (0.2 0 0 0.2 0 0.2);",
        "}",
        "",
    ]
)

# Matches the authoritative native tree's own fixture shape
# (~/noFrontendCardiacFoam_minor_errors/tutorials/manufacturedSolutions/
# monodomainTotalLagrangianEM/constant/electroMechanicalProperties):
# `verificationModel`, not `electromechanicalVerificationModel` -- native
# never reads the latter.
_ELECTROMECHANICAL_TEXT = "\n".join(
    [
        "sequentialElectroMechanicalCoeffs",
        "{",
        "    verificationModel",
        "    {",
        "        type manufacturedElectromechanicsVerifier;",
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

def _write_case(root: Path) -> None:
    (root / "constant" / "electro").mkdir(parents=True, exist_ok=True)
    (root / "constant" / "electro" / "electroProperties").write_text(_ELECTRO_TEXT)
    (root / "constant" / "electroMechanicalProperties").write_text(_ELECTROMECHANICAL_TEXT)
    write_physics_properties(root)
    write_control_dict(root)
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "blockMeshDict.1D").write_text(_BLOCK_MESH_TEXT)


def _case() -> CaseConfig:
    return CaseConfig(
        case_id="1D_40_cells_implicit",
        params={"dimension": "1D", "solver": "implicit", "cells": 40, "dt": 0.002},
    )


def _digests(root: Path) -> dict:
    import hashlib
    return {r: hashlib.sha256((root / r).read_bytes()).hexdigest() for r in _RELPATHS}


class TestManufacturedMonodomainTotalLagrangianEmWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-em-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_apply_case_default_call_succeeds(self) -> None:
        """The tutorial's own default `verification_model_type` used to
        raise on unmodified HEAD (see module docstring); it now succeeds."""
        root = self.tmp / "apply"
        _write_case(root)
        tut._apply_case(root, _case())

        content = (root / "constant" / "electroMechanicalProperties").read_text()
        self.assertIn(
            "verificationModel", content.split("sequentialElectroMechanicalCoeffs", 1)[1],
        )
        self.assertNotIn("electromechanicalVerificationModel", content)

    def test_plan_case_and_apply_case_match_byte_for_byte(self) -> None:
        apply_root = self.tmp / "apply2"
        plan_root = self.tmp / "plan"
        _write_case(apply_root)
        _write_case(plan_root)

        tut._apply_case(apply_root, _case())
        tut._plan_case(plan_root, _case())

        apply_digests = _digests(apply_root)
        plan_digests = _digests(plan_root)
        for relpath in _RELPATHS:
            self.assertEqual(
                plan_digests[relpath], apply_digests[relpath],
                f"{relpath} differs between _apply_case and _plan_case",
            )

    def test_non_default_verification_model_type_lands_at_the_correct_scope(self) -> None:
        """Not the tutorial's own default -- proof the value the caller
        actually requested reaches `verificationModel.type` (not the dead
        `electromechanicalVerificationModel.type` this used to write, and
        not silently ignored)."""
        root = self.tmp / "plan_non_default"
        _write_case(root)
        tut._plan_case(root, _case(), verification_model_type="manufacturedTotalLagrangianVerifier")

        content = (root / "constant" / "electroMechanicalProperties").read_text()
        em_coeffs = content.split("sequentialElectroMechanicalCoeffs", 1)[1]
        self.assertIn("verificationModel", em_coeffs)
        self.assertIn("type    manufacturedTotalLagrangianVerifier", em_coeffs)
        self.assertNotIn("electromechanicalVerificationModel", content)


if __name__ == "__main__":
    unittest.main()
