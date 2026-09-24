"""Phase 3 Task 9, "the `describe` seam" -- the unmet second payoff.

`core.introspection._write_surface` (Phase 2 Task 13) matched supplied keys
against catalog qualified ids, but no real invocation in this codebase ever
supplies catalog-shaped keys: the CLI hands it raw tutorial-factory kwargs
(`ionic_model`, `electro_property_overrides`). Task 9 closes that gap by
reusing the tutorial's own `plan_case`, run for real against a disposable
staged clone of its case (never the real `case_root`), and reading the
qualified ids/values/sources/operations off the committed
`CaseWriteRecord` -- see `core.introspection._resolve_proposed_changes`.

Three things are proven here, against real cardiacfoam adapter code (this
package is where `plan_case` and the real catalog live -- the core-level
fake-plugin tests in
`packages/omnidriver/tests/core/test_describe_write_surface.py` cannot
exercise any of this):

1. `single_cell`'s real `plan_case`, driven by raw factory kwargs exactly as
   the CLI would supply them, produces non-empty, correctly-valued
   `proposed_changes` -- and the real, on-disk fixture case is provably
   untouched (a directory snapshot, not an assumption).
2. A whole-dict removal target (`manufactured_monodomain_pseudo_ecg`'s
   conditional `ecgDomains` removal) is not a `ParameterAssignment` at all
   (Task 6/7's own finding: "not a `ParameterAssignment`, a whole
   sub-dictionary has no single `key_path`") and so cannot carry a
   qualified id -- it surfaces in `expected_effects` (Task 1's finding,
   given its first consumer here), not in the structured
   `proposed_changes` list. Stated, not silently dropped.
3. A genuine `ParameterAssignment`-shaped removal
   (`resolve_electro_property_removal`, `operation="remove"`) *does* carry a
   qualified id, and *does* appear in `proposed_changes` with
   `value: None`. The one real tutorial that calls this function
   (`manufactured_bath_bidomain`) cannot demonstrate it end-to-end today: an
   unrelated, pre-existing, separately-tracked bug (an undeclared key,
   `bidomainSolverCoeffs.manufacturedBidomain.fdaBathVariant`, written
   unconditionally) makes every real invocation of its `plan_case` raise
   before returning -- and that tutorial is one of the two "wrong-scope key"
   files a parallel session owns right now, so it is not fixed here. A
   minimal, self-contained `plan_case` built for this test isolates the
   *mechanism* (`resolve_electro_property_removal` +
   `commit_case_overrides`, both real, unmodified production code) from
   that unrelated tutorial-specific bug.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from write_channel_test_support import write_physics_properties

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.overrides import (
    commit_case_overrides,
    resolve_electro_property_removal,
)
from omnidriver.cardiacfoam.tutorials import (
    manufactured_monodomain_pseudo_ecg as pseudo_ecg,
    single_cell,
)
from omnidriver.core.introspection import _resolve_proposed_changes, _write_surface
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
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


class TestSingleCellProposedChangesEndToEnd(unittest.TestCase):
    """Proof 1: `describe --plugin cardiacfoam --entry singleCell --config
    <real overrides>` (exercised here at the `_write_surface` level, the
    same function `describe_entry`/the CLI calls) returns non-empty
    `proposed_changes` naming the qualified ids that will change and their
    values -- and the real case fixture is untouched."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-describe-proposed-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.case_root = self.tmp / "electrophysiologyProtocols" / "singleCell"
        (self.case_root / "constant").mkdir(parents=True)
        (self.case_root / "constant" / "electroProperties").write_text(
            "\n".join([
                "myocardiumSolver singleCellSolver;",
                "",
                "singleCellSolverCoeffs",
                "{",
                "    ionicModel BuenoOrovio;",
                "    tissue myocyte;",
                "    singleCellStimulus",
                "    {",
                "        stim_amplitude 0.4;",
                "        stim_period_S1 1000;",
                "    }",
                "}",
                "",
            ])
        )
        write_physics_properties(self.case_root)

    def _spec(self, overrides: dict) -> TutorialSpec:
        return single_cell.make_spec(cases_root=self.tmp, **overrides)

    def test_proposed_changes_are_non_empty_and_correctly_valued(self) -> None:
        overrides = dict(
            ionic_model="BuenoOrovio",
            tissue="epicardialCells",
            electro_property_overrides={
                "singleCellSolverCoeffs.singleCellStimulus.stim_period_S1": 900,
            },
            physics_property_overrides={"type": "electroMechanicalModel"},
        )
        spec = self._spec(overrides)
        before = _tree_digest(self.case_root)

        described = _write_surface(driver_context=_CTX, spec=spec, overrides=overrides)

        self.assertEqual(described["proposed_changes_source"], "plan_case_preview")
        self.assertEqual(described["proposed_changes_reason"], "")
        by_id = {item["qualified_id"]: item for item in described["proposed_changes"]}
        self.assertIn(
            "singleCellSolverCoeffs.singleCellStimulus.stim_period_S1", by_id,
        )
        changed = by_id["singleCellSolverCoeffs.singleCellStimulus.stim_period_S1"]
        self.assertEqual(changed["value"], 900)
        self.assertEqual(changed["source"], "case")
        self.assertEqual(changed["operation"], "set")
        self.assertEqual(changed["document"], "constant/electroProperties")
        self.assertIn("singleCellSolverCoeffs.tissue", by_id)
        self.assertEqual(by_id["singleCellSolverCoeffs.tissue"]["value"], "epicardialCells")
        self.assertIn("type", {i["qualified_id"] for i in described["proposed_changes"]})

        # The real fixture case_root -- never passed to plan_case, only a
        # disposable staged clone was -- is provably untouched, not merely
        # unclaimed to have changed.
        after = _tree_digest(self.case_root)
        self.assertEqual(before, after)
        # No stray staging/journal artifacts were left beside it either.
        self.assertEqual(
            sorted(p.name for p in self.tmp.iterdir()),
            ["electrophysiologyProtocols"],
        )

    def test_a_sweep_that_has_not_collapsed_to_one_case_reports_unknown_not_empty(self) -> None:
        """No override collapses `ionic_models`/`ionic_model_tissue_map` to a
        single case here -- `build_cases()` enumerates the whole catalog.
        `single_cell` *does* have a `plan_case` -- a resolver exists, it
        just could not run for this request -- so the result must be
        `None` (unknown), stating why, never a silently empty list that
        would read as "nothing will change" (corrected 2026-09-24, found by
        running `describe` through the real CLI)."""
        spec = self._spec({})
        self.assertIsNotNone(spec.plan_case)
        self.assertGreater(len(spec.build_cases()), 1)
        described = _write_surface(driver_context=_CTX, spec=spec, overrides={})
        self.assertEqual(described["proposed_changes_source"], "unknown")
        self.assertIsNone(described["proposed_changes"])
        self.assertIn("resolved to", described["proposed_changes_reason"])
        self.assertIn("cases", described["proposed_changes_reason"])

    def test_a_staged_preview_that_raises_reports_unknown_not_an_empty_list(self) -> None:
        """Defect found by the coordinator running `describe` through the
        real CLI against a real case (2026-09-24), not by this module's own
        tests: with `case_root` existing but missing
        `constant/electroProperties` (an ordinary situation -- `describe` is
        used before a case is materialized, not only after), the staged
        preview raises `patch target 'constant/electroProperties' does not
        exist`. Before this fix, `_write_surface` swallowed that into the
        naive fallback, which computed `[]` for a raw factory-kwargs
        `overrides` dict -- indistinguishable from "nothing will change".
        `proposed_changes` must be `None` (JSON `null`) instead, and
        `describe` must not raise -- it stays a best-effort command whose
        other fields are still useful when a case does not exist yet."""
        cases_root = Path(tempfile.mkdtemp(prefix="omnidriver-describe-missing-case-"))
        self.addCleanup(shutil.rmtree, cases_root, ignore_errors=True)
        empty_case_root = cases_root / "electrophysiologyProtocols" / "singleCell"
        empty_case_root.mkdir(parents=True)
        overrides = dict(
            ionic_model="BuenoOrovio", tissue="epicardialCells",
            cases_root=cases_root,
        )
        spec = single_cell.make_spec(**overrides)
        self.assertIsNotNone(spec.plan_case)

        described = _write_surface(driver_context=_CTX, spec=spec, overrides=overrides)

        self.assertIsNone(described["proposed_changes"])
        self.assertEqual(described["proposed_changes_source"], "unknown")
        self.assertIn("does not exist", described["proposed_changes_reason"])
        # describe itself must not raise, and the real case_root (still
        # missing the file, on purpose) is untouched -- no file was created
        # by the failed preview attempt.
        self.assertEqual(list(empty_case_root.iterdir()), [])


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


def _minimal_removal_plan_case(case_root: Path, case: CaseConfig) -> object:
    """A self-contained `plan_case`, built only for this test, exercising
    exactly the same production mechanism `manufactured_bath_bidomain`'s own
    `_plan_case` uses for its stale-patch-entry cleanup
    (`resolve_electro_property_removal` -> `commit_case_overrides`) --
    isolated from that tutorial's own, unrelated, separately-tracked
    dead-key bug (`bidomainSolverCoeffs.manufacturedBidomain.fdaBathVariant`,
    a parallel session's file to fix, not this test's)."""
    electro_document = "constant/electroProperties"
    electro_properties = case_root / electro_document
    parameter = resolve_electro_property_removal(
        electro_properties, "xMin", document=electro_document,
        scope=["bidomainSolverCoeffs", "bathPotentialDomain", "groundPatches"],
    )
    return commit_case_overrides(
        case_root, parameters=[parameter], workflow="test_minimal_removal",
        requested_by="test_describe_proposed_changes",
    )


class TestAParameterShapedRemovalIsAStructuredProposedChange(unittest.TestCase):
    """Proof 3: a genuine `ParameterAssignment(operation="remove")` -- one
    that *does* carry a qualified id -- appears in `proposed_changes` with
    `value: None`, `operation: "remove"`."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-describe-remove-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.case_root = self.tmp / "case"
        (self.case_root / "constant").mkdir(parents=True)
        (self.case_root / "constant" / "electroProperties").write_text(
            "\n".join([
                "myocardiumSolver bidomainSolver;",
                "",
                "bidomainSolverCoeffs",
                "{",
                "    bathPotentialDomain",
                "    {",
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
            ])
        )

    def test_removal_appears_with_a_qualified_id_and_a_null_value(self) -> None:
        spec = TutorialSpec(
            name="test_minimal_removal_spec",
            case_root=self.case_root,
            setup_root=self.case_root / "setup",
            output_dir=self.case_root,
            build_cases=lambda: [CaseConfig(case_id="only", params={})],
            plan_case=_minimal_removal_plan_case,
        )
        before = _tree_digest(self.case_root)

        proposed_changes, expected_effects, reason = _resolve_proposed_changes(
            driver_context=_CTX, spec=spec,
        )

        self.assertEqual(reason, "")
        self.assertIsNotNone(proposed_changes)
        self.assertEqual(len(proposed_changes), 1)
        change = proposed_changes[0]
        self.assertEqual(
            change["qualified_id"],
            "bidomainSolverCoeffs.bathPotentialDomain.groundPatches.xMin",
        )
        self.assertEqual(change["operation"], "remove")
        self.assertIsNone(change["value"])
        self.assertEqual(change["source"], "case")
        self.assertIn(
            "remove 'bidomainSolverCoeffs.bathPotentialDomain.groundPatches.xMin' "
            "in constant/electroProperties",
            expected_effects,
        )
        # The real fixture is untouched -- only a staged clone was mutated.
        self.assertEqual(before, _tree_digest(self.case_root))


if __name__ == "__main__":
    unittest.main()
