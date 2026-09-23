"""Phase 3 Task 6: `manufactured_monodomain_total_lagrangian_em` -- entry
overrides on two documents (electroProperties, electroMechanicalProperties),
a block-mesh rewrite, and `deltaT`, folded into one transaction.

**Found while writing this test, not assumed, and out of Task 6's own
mandate to fix:** the tutorial's hardcoded key,
``sequentialElectroMechanicalCoeffs.electromechanicalVerificationModel.type``,
does not match what the native reader actually looks up --
``electromechanicalVerificationModel.C``'s ``New``/``configured`` read
``verificationModel.type`` off the ``<type>Coeffs`` subDict (confirmed
against ``~/noFrontendCardiacFoam_minor_errors/src/verificationModels/
electromechanicsVerification/electromechanicalVerificationModel.C`` and
``~/noFrontendCardiacFoam_minor_errors/src/electroMechanicalModels/
electroMechanicalModel/electroMechanicalModel.C``'s
``electroMechanicalProperties_(subDict(type + "Coeffs"))``), not
``electromechanicalVerificationModel.type``. Pre-Task-2, the unchecked
writer wrote this wrong key silently (a dead entry no native code reads);
Task 2's catalog-strictness decision (2026-09-23) now refuses it outright,
since `dict_entries_catalog.py`/`common_dict_entries.py` never declared
this misspelled path in the first place -- correctly, since nothing reads
it. This means `_apply_case`'s own DEFAULT call (no
`electromechanical_property_overrides` at all) already raises `ValueError`
on unmodified HEAD, independent of Task 6. Fixing the tutorial's key name
is a separate, out-of-scope correction (flagged separately); this test
characterizes the two paths raising identically, which is what "reproduces
`_apply_case`'s behaviour exactly" means for a call that itself fails.
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

_ELECTROMECHANICAL_TEXT = "\n".join(
    [
        "sequentialElectroMechanicalCoeffs",
        "{",
        "    electromechanicalVerificationModel",
        "    {",
        "        type manufacturedTotalLagrangianVerifier;",
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


class TestManufacturedMonodomainTotalLagrangianEmWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-em-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_apply_case_default_call_raises(self) -> None:
        """Captured 2026-09-23: the tutorial's default
        `verification_model_type` key is undeclared (see module docstring),
        so `_apply_case`'s own default call already raises on HEAD."""
        root = self.tmp / "apply"
        _write_case(root)
        with self.assertRaises(ValueError) as apply_exc:
            tut._apply_case(root, _case())
        self.assertIn(
            "sequentialElectroMechanicalCoeffs.electromechanicalVerificationModel.type",
            str(apply_exc.exception),
        )

    def test_plan_case_raises_the_identical_error(self) -> None:
        apply_root = self.tmp / "apply2"
        plan_root = self.tmp / "plan"
        _write_case(apply_root)
        _write_case(plan_root)
        with self.assertRaises(ValueError) as apply_exc:
            tut._apply_case(apply_root, _case())
        with self.assertRaises(ValueError) as plan_exc:
            tut._plan_case(plan_root, _case())
        self.assertEqual(str(apply_exc.exception), str(plan_exc.exception))


if __name__ == "__main__":
    unittest.main()
