"""Phase 3 Task 9, "the `describe` seam" -- the unmet second payoff.

`core.introspection._write_surface` (Phase 2 Task 13) matched supplied keys
against catalog qualified ids, but no real invocation in this codebase ever
supplies catalog-shaped keys: the CLI hands it raw tutorial-factory kwargs
(`ionic_model`, `electro_property_overrides`). Task 9 closes that gap by
reusing the tutorial's own `plan_case`, run for real against a disposable
staged clone of its case (never the real `case_root`), and reading the
qualified ids/values/sources/operations off the committed
`CaseWriteRecord` -- see `core.introspection._resolve_proposed_changes`.

Two things are proven here, against real cardiacfoam adapter code (this
package is where `plan_case` and the real catalog live -- the core-level
fake-plugin tests in
`packages/omnidriver/tests/core/test_describe_write_surface.py` cannot
exercise any of this):

Proof 1 (a factory tutorial's real `plan_case`, driven by raw factory
kwargs exactly as the CLI would supply them, produces non-empty,
correctly-valued `proposed_changes` against a provably-untouched on-disk
fixture case) used to live here, exercising `single_cell`'s own `plan_case`
-- deleted 2026-09-27 alongside that factory (tutorials-are-pointers plan,
step 5.1): `single_cell` migrated onto a tutorial record, whose `describe`
path this module's `_write_surface` helper does not drive at all (a
record's own preview goes through `record_execution`, not raw factory
kwargs), so there is no longer a `plan_case`-driven proof to make here.

1. A whole-dict removal target (`manufactured_monodomain_pseudo_ecg`'s
   conditional `ecgDomains` removal) is not a `ParameterAssignment` at all
   (Task 6/7's own finding: "not a `ParameterAssignment`, a whole
   sub-dictionary has no single `key_path`") and so cannot carry a
   qualified id -- it surfaces in `expected_effects` (Task 1's finding,
   given its first consumer here), not in the structured
   `proposed_changes` list. Stated, not silently dropped.
Proof 3 (a `ParameterAssignment(operation="remove")` from
`resolve_electro_property_removal` appearing in `proposed_changes` with
`value: None`) was deleted 2026-09-26 with that function (tutorials-are-
pointers 5.4a): its one caller, `manufactured_bath_bidomain`, migrated onto
a tutorial record whose studies replace the bath patch maps whole (owner
Q4), so no production code builds such a removal any more.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from write_channel_test_support import write_physics_properties

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.tutorials import (
    manufactured_monodomain_pseudo_ecg as pseudo_ecg,
)
from omnidriver.core.introspection import _resolve_proposed_changes, _write_surface
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.runtime.models import TutorialSpec
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_CTX = _driver_context(
    OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:describe_proposed_changes",
)


def _tree_digest(root: Path) -> dict[str, str]:
    """A full recursive content digest of every file under `root` -- the
    "assert on a directory snapshot" proof this task's own instructions
    require, not merely a claim that nothing was touched."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class TestWholeDictRemovalSurfacesAsAnExpectedEffectNotAQualifiedChange(unittest.TestCase):
    """Proof 2 (and the honest limit of proof 3): `manufactured_monodomain_
    pseudo_ecg`'s conditional `ecgDomains` removal is a `plan_dict_block`
    raw target, not a `ParameterAssignment` -- it has no single qualified
    id, by construction (Decision, 2026-09-23, "a parameter asserts a final
    state, not only a value": this is exactly the shape that decision left
    outside `ParameterAssignment`'s vocabulary). It must still be visible
    somewhere in the described write surface, not silently dropped --
    `expected_effects` is that place."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-describe-removal-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.case_root = self.tmp / "manufacturedSolutions" / "monodomainPseudoECG"
        (self.case_root / "constant").mkdir(parents=True)
        (self.case_root / "constant" / "electroProperties").write_text(
            "\n".join([
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
            ])
        )
        write_physics_properties(self.case_root)
        (self.case_root / "system").mkdir(parents=True)
        (self.case_root / "system" / "controlDict").write_text(
            "FoamFile\n{\n    object controlDict;\n}\n\ndeltaT          1e-06;\nendTime         1;\n",
        )
        (self.case_root / "system" / "blockMeshDict.1D").write_text(
            "FoamFile\n{\n    object blockMeshDict;\n}\n"
            "blocks\n(\n    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n);\n",
        )

    def test_the_removal_is_named_in_expected_effects_not_in_proposed_changes(self) -> None:
        spec = pseudo_ecg.make_spec(
            cases_root=self.tmp,
            dimensions=["1D"], number_cells=[40], dt_values=[0.002],
            solver_types=["implicit"], run_in_parallel=False,
            end_time=0.05, ecg_enabled=False,
            physics_property_overrides={"type": "electroMechanicalModel"},
        )
        self.assertEqual(len(spec.build_cases()), 1)
        before = _tree_digest(self.case_root)

        described = _write_surface(driver_context=_CTX, spec=spec, overrides={})

        self.assertEqual(described["proposed_changes_source"], "plan_case_preview")
        self.assertIn(
            "remove ecgDomains block from constant/electroProperties",
            described["expected_effects"],
        )
        # Not a qualified_id-bearing proposed change -- there genuinely is no
        # single qualified id for a whole-dict removal to carry.
        self.assertNotIn(
            "ecgDomains",
            {item["qualified_id"] for item in described["proposed_changes"]},
        )
        self.assertEqual(before, _tree_digest(self.case_root))


if __name__ == "__main__":
    unittest.main()
