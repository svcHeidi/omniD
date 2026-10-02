"""Tests for the dict builder, which synthesizes a complete electroProperties dict from
selectors and overrides and enforces the validator's constraints, so its output is
validator-clean by construction."""
from __future__ import annotations

import unittest
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default to discover.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:dict_builder")
SINGLE_CELL_ELECTRO_PROPERTIES = (
    Path(__file__).resolve().parent / "fixtures" / "tutorials" / "electrophysiologyProtocols"
    / "singleCell" / "constant" / "electroProperties"
)


class TestDictBuilderModule(unittest.TestCase):
    def test_module_exposes_build_electro_properties(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        self.assertTrue(callable(build_electro_properties))

    def test_function_accepts_documented_kwargs(self) -> None:
        import inspect
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        sig = inspect.signature(build_electro_properties)
        params = sig.parameters
        self.assertIn("selectors", params)
        self.assertIn("overrides", params)
        self.assertIn("typical_value_fallback", params)
        self.assertEqual(params["overrides"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(params["typical_value_fallback"].kind, inspect.Parameter.KEYWORD_ONLY)


class TestMinimalSingleCellBuild(unittest.TestCase):
    def test_returns_string_with_foamfile_preamble(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "singleCellSolver",
                "ionicModel": "AlievPanfilov",
                "tissue": "myocyte",
            },
        )
        self.assertIsInstance(text, str)
        self.assertIn("FoamFile", text)
        self.assertIn("myocardiumSolver", text)
        self.assertIn("singleCellSolver", text)


    def test_an_absent_stimulus_block_is_not_invented_from_defaults(self) -> None:
        """stimulusIO.C returns a no-op protocol when ``singleCellStimulus`` is absent, so no stimulus is legal."""
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        text = build_electro_properties({
            "myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte",
        })
        invented = [
            line.strip() for line in text.splitlines()
            if any(key in line for key in ("stim_start", "stim_duration", "stim_amplitude", "stim_period", "nstim"))
        ]
        self.assertEqual(invented, [])


class TestContextResolution(unittest.TestCase):
    def test_resolve_context_collapses_selectors_and_overrides(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import resolve_context
        ctx = resolve_context(
            selectors={"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP"},
            overrides={
                "$ELECTRO_MODEL_COEFFS.solutionAlgorithm": "implicit",
                "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude": "60",
            },
        )
        # Overrides lose the $ELECTRO_MODEL_COEFFS prefix to match the slot_key convention.
        self.assertEqual(ctx["myocardiumSolver"], "monodomainSolver")
        self.assertEqual(ctx["ionicModel"], "TNNP")
        self.assertEqual(ctx["solutionAlgorithm"], "implicit")
        self.assertEqual(ctx["singleCellStimulus.stim_amplitude"], "60")

    def test_resolve_context_overrides_silent_when_none(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import resolve_context
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver"},
            overrides=None,
        )
        self.assertEqual(ctx, {"myocardiumSolver": "singleCellSolver"})


class TestApplicableEntrySelection(unittest.TestCase):
    def test_eikonal_context_excludes_ionic_model_entry(self) -> None:
        """ionicModel is forbidden_when under eikonal; the applicable_when-filtered entry is tissue."""
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "eikonalSolver"},
        )
        entries = select_applicable_entries(ctx)
        paths = {e.driver_path for e in entries}
        self.assertNotIn("$ELECTRO_MODEL_COEFFS.tissue", paths)

    def test_monodomain_context_includes_ionic_model_entry(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP"},
        )
        entries = select_applicable_entries(ctx)
        paths = {e.driver_path for e in entries}
        self.assertIn("$ELECTRO_MODEL_COEFFS.ionicModel", paths)
        self.assertIn("$ELECTRO_MODEL_COEFFS.tissue", paths)

    def test_field_source_omits_monodomain_uniform_tensor(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "monodomainSolver",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
                "conductivitySource": "field",
            },
        )
        self.assertIn("conductivitySource field;", text)
        self.assertNotIn("\n    conductivity ", text)

    def test_field_source_omits_both_bidomain_uniform_tensors(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "bidomainSolver",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
                "conductivitySource": "field",
            },
        )
        self.assertIn("conductivitySource field;", text)
        self.assertNotIn("conductivityIntracellular", text)
        self.assertNotIn("conductivityExtracellular", text)

    def test_spatial_solver_defaults_to_uniform_source(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "monodomainSolver",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        )
        self.assertIn("conductivitySource uniform;", text)
        self.assertIn("\n    conductivity ", text)


class TestValuePopulation(unittest.TestCase):
    """Precedence: explicit override, then typical_value (when fallback is enabled), then omit."""

    def test_override_wins_over_typical_value(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            overrides={
                "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude": "0.4",
            },
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=True)
        self.assertEqual(populated["singleCellStimulus.stim_amplitude"], "0.4")

    def test_typical_value_fills_when_no_override(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        # The stimulus family is gated on a configured block; stimulusIO treats an absent one as a no-op.
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            overrides={"$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_start": "20"},
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=True)
        # singleCellStimulus.stim_amplitude has typical_value="60" in dict_entries.
        self.assertEqual(populated["singleCellStimulus.stim_amplitude"], "60")

    def test_fallback_disabled_omits_typical_value(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=False)
        self.assertNotIn("singleCellStimulus.stim_amplitude", populated)

    def test_selector_values_are_present_in_populated_dict(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=True)
        self.assertEqual(populated["myocardiumSolver"], "monodomainSolver")
        self.assertEqual(populated["ionicModel"], "TNNP")
        self.assertEqual(populated["tissue"], "epicardialCells")


class TestRequiredCheck(unittest.TestCase):
    """The rule pass reports only required, applicable entries missing from the populated dict."""

    @staticmethod
    def _errors(entries, populated):
        from omnidriver.cardiacfoam.dict_builder import _with_virtual_presence
        from omnidriver.openfoam.case_rules import rule_diagnostics

        return [e.message for e in rule_diagnostics(
            entries, _with_virtual_presence(populated), document="constant/electroProperties",
        )]

    def test_fully_populated_entries_report_nothing(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=True)
        self.assertEqual(self._errors(entries, populated), [])

    def test_reports_the_missing_required_paths(self) -> None:
        from omnidriver.openfoam.dict_builder import populate_values
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            overrides={"$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_start": "20"},
        )
        entries = select_applicable_entries(ctx)
        populated = populate_values(entries, ctx, typical_value_fallback=False)
        self.assertTrue(any("singleCellStimulus" in message for message in self._errors(entries, populated)))

    def test_optional_unset_entries_report_nothing(self) -> None:
        from omnidriver.dict_entries import DictEntry

        only_optional = [
            DictEntry(
                driver_path="$ELECTRO_MODEL_COEFFS.optionalField",
                description="x",
                value_kind="word",
                source_refs=("ref.C",),
                required=False,
                phases=frozenset({"physics"}),
            ),
        ]
        self.assertEqual(self._errors(only_optional, {}), [])


class TestValidatorIntegration(unittest.TestCase):
    """build_electro_properties runs the rule pass before returning."""

    def test_build_raises_on_mutex_violation_via_overrides(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        with self.assertRaises(ValueError) as ctx:
            build_electro_properties(
                selectors={
                    "myocardiumSolver": "monodomainSolver",
                    "ionicModel": "TNNP",
                    "tissue": "epicardialCells",
                },
                overrides={
                    "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusDuration": "0.002",
                    "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusDurationList": "(0.002 0.001)",
                },
            )
        self.assertIn("mutually exclusive", str(ctx.exception).lower())

    def test_build_raises_on_forbidden_when_violation(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        with self.assertRaises(ValueError) as ctx:
            build_electro_properties(
                selectors={
                    "myocardiumSolver": "eikonalSolver",
                    "ionicModel": "TNNP",
                },
            )
        self.assertIn("forbidden", str(ctx.exception).lower())


class TestSerialisation(unittest.TestCase):
    def test_singlecell_output_matches_snapshot(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "singleCellSolver",
                "ionicModel": "AlievPanfilov",
                "tissue": "myocyte",
            },
        )
        self.assertIn("myocardiumSolver singleCellSolver;", text)
        self.assertIn("singleCellSolverCoeffs", text)
        self.assertIn("ionicModel AlievPanfilov;", text)
        self.assertIn("tissue myocyte;", text)
        # stimulusIO treats an absent singleCellStimulus as a no-op; inventing one would pace a quiescent case.
        self.assertNotIn("singleCellStimulus", text)
        self.assertNotIn("stim_amplitude", text)

    def test_singlecell_stimulus_appears_once_configured(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "singleCellSolver",
                "ionicModel": "AlievPanfilov",
                "tissue": "myocyte",
            },
            overrides={
                "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_start": "20",
            },
        )
        # The rest of the family fills from typical_value, so stimulusIO's four joint keys are never half-written.
        self.assertIn("singleCellStimulus", text)
        self.assertIn("stim_start 20;", text)
        self.assertIn("stim_amplitude 60;", text)

    def test_monodomain_output_matches_snapshot(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        text = build_electro_properties(
            selectors={
                "myocardiumSolver": "monodomainSolver",
                "ionicModel": "TNNP",
                "tissue": "epicardialCells",
            },
        )
        self.assertIn("myocardiumSolver monodomainSolver;", text)
        self.assertIn("monodomainSolverCoeffs", text)
        self.assertNotIn("singleCellSolverCoeffs", text)


class TestPhysicsPropertiesBuilder(unittest.TestCase):
    """Physics keys live at the dict root, with no <solver>Coeffs wrapper."""

    def test_function_accepts_documented_kwargs(self) -> None:
        import inspect
        from omnidriver.cardiacfoam.dict_builder import build_physics_properties
        sig = inspect.signature(build_physics_properties)
        params = sig.parameters
        self.assertIn("selectors", params)
        self.assertIn("overrides", params)
        self.assertIn("typical_value_fallback", params)
        self.assertEqual(params["overrides"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_minimal_electroModel_build(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_physics_properties
        text = build_physics_properties(selectors={"type": "electroModel"})
        self.assertIn("type electroModel;", text)
        self.assertIn("FoamFile", text)
        self.assertIn("object      physicsProperties", text)
        self.assertNotIn("electroProperties", text)
        self.assertNotIn("Coeffs", text)

    def test_missing_required_type_raises(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_physics_properties
        with self.assertRaises(ValueError) as ctx:
            build_physics_properties(selectors={})
        self.assertIn("type", str(ctx.exception))

    def test_invalid_enum_value_raises(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_physics_properties
        with self.assertRaises(ValueError) as ctx:
            build_physics_properties(selectors={"type": "notARealModel"})
        self.assertIn("notARealModel", str(ctx.exception))


class TestBuildAndLaunch(unittest.TestCase):
    """build_and_launch writes both dicts to a case directory and launches via the generic_case spec factory."""

    def test_writes_both_dicts_to_case_dir(self) -> None:
        """dry_run=True writes the dicts without running cardiacFoam."""
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            result = build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "singleCellSolver",
                    "ionicModel": "AlievPanfilov",
                    "tissue": "myocyte",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
            )
            self.assertTrue((case_dir / "constant" / "electroProperties").exists())
            self.assertTrue((case_dir / "constant" / "physicsProperties").exists())
            self.assertEqual(result["case_dir"], str(case_dir))
            self.assertEqual(result["status"], "dry_run_complete")

    def test_existing_case_dir_is_not_overwritten_without_consent(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            (case_dir / "constant").mkdir(parents=True)
            (case_dir / "constant" / "electroProperties").write_text("# pre-existing\n")

            with self.assertRaises(FileExistsError):
                build_and_launch(
                    electro_selectors={
                        "myocardiumSolver": "singleCellSolver",
                        "ionicModel": "AlievPanfilov",
                        "tissue": "myocyte",
                    },
                    physics_selectors={"type": "electroModel"},
                    case_dir=case_dir,
                    dry_run=True,
                )

    def test_overwrite_true_replaces_existing_dicts(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            (case_dir / "constant").mkdir(parents=True)
            old_text = "# pre-existing electroProperties\n"
            (case_dir / "constant" / "electroProperties").write_text(old_text)

            build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "singleCellSolver",
                    "ionicModel": "AlievPanfilov",
                    "tissue": "myocyte",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
                overwrite=True,
            )
            text = (case_dir / "constant" / "electroProperties").read_text()
            self.assertNotEqual(text, old_text)
            self.assertIn("myocardiumSolver singleCellSolver;", text)


class TestBuildAndLaunchMeshProvisioning(unittest.TestCase):
    """electroModel requires a real fvMesh regardless of solver, even singleCellSolver."""

    def test_single_cell_solver_gets_a_block_mesh_dict(self) -> None:
        """A one-cell `system/blockMeshDict` joins the plan; `blockMesh` runs from `Allrun`, never Python."""
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            result = build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "singleCellSolver",
                    "ionicModel": "AlievPanfilov",
                    "tissue": "myocyte",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
            )
            block_mesh_dict = case_dir / "system" / "blockMeshDict"
            self.assertTrue(block_mesh_dict.exists())
            self.assertIn("hex (0 1 2 3 4 5 6 7) (1 1 1)", block_mesh_dict.read_text())
            self.assertFalse((case_dir / "constant" / "polyMesh").exists())
            self.assertTrue(result.get("needs_block_mesh", False))

    def test_single_cell_solver_dx_validation_still_fires_under_dry_run(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            with self.assertRaisesRegex(ValueError, "dx"):
                build_and_launch(
                    electro_selectors={
                        "myocardiumSolver": "singleCellSolver",
                        "ionicModel": "AlievPanfilov",
                        "tissue": "myocyte",
                    },
                    physics_selectors={"type": "electroModel"},
                    case_dir=case_dir,
                    dry_run=True,
                    dx=0.0004,
                )
            self.assertFalse((case_dir / "constant" / "polyMesh").exists())

    def test_spatial_solver_gets_a_block_mesh_dict(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            result = build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "monodomainSolver",
                    "ionicModel": "TNNP",
                    "tissue": "epicardialCells",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
            )
            block_mesh_dict = case_dir / "system" / "blockMeshDict"
            self.assertTrue(block_mesh_dict.exists())
            self.assertIn("blocks", block_mesh_dict.read_text())
            self.assertFalse((case_dir / "constant" / "polyMesh").exists())
            self.assertTrue(result.get("needs_block_mesh", False))

    def test_dx_kwarg_controls_generated_block_mesh_resolution(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch
        from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "monodomainSolver",
                    "ionicModel": "TNNP",
                    "tissue": "epicardialCells",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
                dx=0.0004,
            )
            written = (case_dir / "system" / "blockMeshDict").read_text()
            self.assertEqual(written, default_block_mesh_dict_text(dx_m=0.0004))
            self.assertNotEqual(written, default_block_mesh_dict_text())

    def test_dx_kwarg_rejected_for_single_cell_solver(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            with self.assertRaisesRegex(ValueError, "dx"):
                build_and_launch(
                    electro_selectors={
                        "myocardiumSolver": "singleCellSolver",
                        "ionicModel": "AlievPanfilov",
                        "tissue": "myocyte",
                    },
                    physics_selectors={"type": "electroModel"},
                    case_dir=case_dir,
                    dry_run=True,
                    dx=0.0004,
                )

    def test_existing_mesh_is_not_clobbered_without_overwrite(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            block_mesh_dict = case_dir / "system" / "blockMeshDict"
            block_mesh_dict.parent.mkdir(parents=True)
            block_mesh_dict.write_text("// pre-existing custom mesh\n")
            (case_dir / "constant").mkdir(parents=True)
            (case_dir / "constant" / "electroProperties").write_text("# pre-existing\n")
            build_and_launch(
                electro_selectors={
                    "myocardiumSolver": "monodomainSolver",
                    "ionicModel": "TNNP",
                    "tissue": "epicardialCells",
                },
                physics_selectors={"type": "electroModel"},
                case_dir=case_dir,
                dry_run=True,
                overwrite=True,
            )
            self.assertEqual(block_mesh_dict.read_text(), "// pre-existing custom mesh\n")


class TestParseElectroProperties(unittest.TestCase):
    """parse_electro_properties reads an existing file back into selectors+overrides."""

    @staticmethod
    def _build_and_write(tmp_dir, selectors, overrides=None):
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties
        text = build_electro_properties(selectors, overrides=overrides)
        p = Path(tmp_dir) / "electroProperties"
        p.write_text(text)
        return p

    def test_returns_dict_with_selectors_and_overrides_keys(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "singleCellSolver",
                 "ionicModel": "AlievPanfilov",
                 "tissue": "myocyte"},
            )
            result = parse_electro_properties(p)
            self.assertIn("selectors", result)
            self.assertIn("overrides", result)

    def test_solver_in_selectors(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "monodomainSolver",
                 "ionicModel": "TNNP",
                 "tissue": "epicardialCells"},
            )
            result = parse_electro_properties(p)
            self.assertEqual(result["selectors"]["myocardiumSolver"], "monodomainSolver")

    def test_ionic_model_and_tissue_in_selectors(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "singleCellSolver",
                 "ionicModel": "AlievPanfilov",
                 "tissue": "myocyte"},
            )
            result = parse_electro_properties(p)
            self.assertEqual(result["selectors"]["ionicModel"], "AlievPanfilov")
            self.assertEqual(result["selectors"]["tissue"], "myocyte")

    def test_ignored_keys_lists_structurally_skipped_dynamic_paths(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "monodomainSolver",
                 "ionicModel": "TNNP",
                 "tissue": "epicardialCells"},
            )
            result = parse_electro_properties(p)
            self.assertIn("selectors", result)
            self.assertIn("overrides", result)
            # The parser surfaces the driver_path families it does not round-trip.
            self.assertIn("ignored_keys", result)
            self.assertIsInstance(result["ignored_keys"], list)
            self.assertTrue(result["ignored_keys"])
            self.assertTrue(
                all(k.startswith("$ELECTRO_MODEL_COEFFS") for k in result["ignored_keys"])
            )

    def test_non_default_override_is_captured(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "monodomainSolver",
                 "ionicModel": "AlievPanfilov",
                 "tissue": "myocyte"},
                overrides={
                    "$ELECTRO_MODEL_COEFFS.solutionAlgorithm": "implicit",
                },
            )
            result = parse_electro_properties(p)
            self.assertEqual(
                result["overrides"].get("$ELECTRO_MODEL_COEFFS.solutionAlgorithm"),
                "implicit",
            )

    def test_default_value_absent_from_overrides(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "singleCellSolver",
                 "ionicModel": "AlievPanfilov",
                 "tissue": "myocyte"},
            )
            result = parse_electro_properties(p)
            self.assertNotIn(
                "$ELECTRO_MODEL_COEFFS.solutionAlgorithm",
                result["overrides"],
            )

    def test_selector_keys_not_duplicated_in_overrides(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties
        with tempfile.TemporaryDirectory() as d:
            p = self._build_and_write(
                d,
                {"myocardiumSolver": "singleCellSolver",
                 "ionicModel": "AlievPanfilov",
                 "tissue": "myocyte"},
            )
            result = parse_electro_properties(p)
            override_slot_keys = {
                k.replace("$ELECTRO_MODEL_COEFFS.", "")
                for k in result["overrides"]
            }
            for sel_key in ("myocardiumSolver", "ionicModel", "tissue"):
                self.assertNotIn(sel_key, override_slot_keys)

    def test_active_tension_model_survives_singlecell_roundtrip(self) -> None:
        """singleCellSolver reads activeTensionModel as a flat word in its Coeffs, not a sub-block."""
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import (
            build_electro_properties,
            parse_electro_properties,
        )
        selectors = {
            "myocardiumSolver": "singleCellSolver",
            "ionicModel": "TWorld",
            "tissue": "endocardialCells",
        }
        overrides = {"$ELECTRO_MODEL_COEFFS.activeTensionModel": "LandNiederer"}

        text = build_electro_properties(selectors, overrides=overrides)
        self.assertIn("activeTensionModel LandNiederer;", text)
        self.assertNotIn("activeTensionModel\n    {", text)

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "electroProperties"
            p.write_text(text)
            parsed = parse_electro_properties(p)

        self.assertEqual(
            parsed["overrides"].get("$ELECTRO_MODEL_COEFFS.activeTensionModel"),
            "LandNiederer",
        )

    def test_active_tension_model_recovered_from_the_singlecell_fixture(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import parse_electro_properties

        result = parse_electro_properties(SINGLE_CELL_ELECTRO_PROPERTIES)
        self.assertEqual(
            result["overrides"].get("$ELECTRO_MODEL_COEFFS.activeTensionModel"),
            "LandNiedererTWorld",
        )

    def test_roundtrip_produces_equivalent_text(self) -> None:
        """Compares re-parsed dicts, not raw text: `foamDictionary` canonicalizes numbers (`1e-6` -> `1e-06`)."""
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import (
            build_electro_properties,
            parse_electro_properties,
        )
        original_selectors = {
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "TNNP",
            "tissue": "epicardialCells",
        }
        original_overrides = {
            "$ELECTRO_MODEL_COEFFS.solutionAlgorithm": "explicit",
        }
        original_text = build_electro_properties(
            original_selectors, overrides=original_overrides,
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "electroProperties"
            p.write_text(original_text)
            parsed = parse_electro_properties(p)

        rebuilt_text = build_electro_properties(
            parsed["selectors"], overrides=parsed["overrides"] or None,
        )
        with tempfile.TemporaryDirectory() as d2:
            p2 = Path(d2) / "electroProperties"
            p2.write_text(rebuilt_text)
            reparsed = parse_electro_properties(p2)

        self.assertEqual(parsed, reparsed)


class TestBuildAndLaunchControlDict(unittest.TestCase):
    """build_and_launch delta_t / end_time patch an existing system/controlDict."""

    @staticmethod
    def _selectors():
        return (
            {"myocardiumSolver": "singleCellSolver",
             "ionicModel": "AlievPanfilov",
             "tissue": "myocyte"},
            {"type": "electroModel"},
        )

    @staticmethod
    def _make_case_with_control_dict(d: str) -> "object":
        from pathlib import Path
        case_dir = Path(d) / "case"
        (case_dir / "system").mkdir(parents=True)
        (case_dir / "system" / "controlDict").write_text(
            "deltaT    0.05;\nendTime   1.0;\n"
        )
        return case_dir

    def test_delta_t_written_to_control_dict(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import build_and_launch
        electro, physics = self._selectors()
        with tempfile.TemporaryDirectory() as d:
            case_dir = self._make_case_with_control_dict(d)
            build_and_launch(
                electro,
                physics_selectors=physics,
                case_dir=case_dir,
                delta_t=0.001,
                dry_run=True,
            )
            text = (case_dir / "system" / "controlDict").read_text()
            self.assertIn("0.001", text)

    def test_end_time_written_to_control_dict(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import build_and_launch
        electro, physics = self._selectors()
        with tempfile.TemporaryDirectory() as d:
            case_dir = self._make_case_with_control_dict(d)
            build_and_launch(
                electro,
                physics_selectors=physics,
                case_dir=case_dir,
                end_time=0.002,
                dry_run=True,
            )
            text = (case_dir / "system" / "controlDict").read_text()
            self.assertIn("0.002", text)

    def test_none_params_leave_control_dict_unchanged(self) -> None:
        import tempfile
        from omnidriver.cardiacfoam.dict_builder import build_and_launch
        electro, physics = self._selectors()
        with tempfile.TemporaryDirectory() as d:
            case_dir = self._make_case_with_control_dict(d)
            original = (case_dir / "system" / "controlDict").read_text()
            build_and_launch(
                electro,
                physics_selectors=physics,
                case_dir=case_dir,
                dry_run=True,
            )
            self.assertEqual(
                (case_dir / "system" / "controlDict").read_text(),
                original,
            )

    def test_control_dict_is_generated_when_delta_t_set(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.dict_builder import build_and_launch
        electro, physics = self._selectors()
        with tempfile.TemporaryDirectory() as d:
            case_dir = Path(d) / "case"
            case_dir.mkdir()
            build_and_launch(
                electro,
                physics_selectors=physics,
                case_dir=case_dir,
                delta_t=0.001,
                dry_run=True,
            )
            control_dict_path = case_dir / "system" / "controlDict"
            self.assertTrue(control_dict_path.exists())
            self.assertIn("deltaT", control_dict_path.read_text())


class TestEikonalECGHeterogeneity(unittest.TestCase):
    """sigmaExtracellular and ionicHeterogeneity entries under eikonalSolver + eikonalECG."""

    def test_sigmaExtracellular_in_catalog_when_ecgDomains_present(self) -> None:
        """Any ecgDomains override sets the virtual ``$ecgDomains_present`` key."""
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )
        from omnidriver.core.contracts.catalogue_paths import slot_key

        context = resolve_context(
            selectors={"myocardiumSolver": "eikonalSolver"},
            overrides={
                "$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.ecgSolver": "eikonalECG",
            },
        )
        entries = select_applicable_entries(context)
        paths = {e.driver_path for e in entries}
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.sigmaExtracellular",
            paths,
        )

    def test_sigmaExtracellular_absent_without_ecgDomains(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )

        context = resolve_context(selectors={"myocardiumSolver": "eikonalSolver"})
        entries = select_applicable_entries(context)
        paths = {e.driver_path for e in entries}
        self.assertNotIn(
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.sigmaExtracellular",
            paths,
        )

    def test_ionic_heterogeneity_entries_applicable_for_eikonalSolver(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )

        context = resolve_context(selectors={"myocardiumSolver": "eikonalSolver"})
        entries = select_applicable_entries(context)
        paths = {e.driver_path for e in entries}
        expected = {
            "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.field",
            "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.mode",
            "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionWidth",
            "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionMode",
            "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.smoothing",
        }
        self.assertTrue(expected.issubset(paths), f"Missing: {expected - paths}")

    def test_ionic_heterogeneity_entries_applicable_for_monodomainSolver(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )

        context = resolve_context(
            selectors={"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        )
        entries = select_applicable_entries(context)
        paths = {e.driver_path for e in entries}
        self.assertIn("$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionMode", paths)
        self.assertIn("$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.smoothing", paths)

    def test_eikonalSolver_with_ionicHeterogeneity_overrides_round_trips(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        text = build_electro_properties(
            selectors={"myocardiumSolver": "eikonalSolver"},
            overrides={
                # Minimum required eikonalSolver fields without typical_values
                "$ELECTRO_MODEL_COEFFS.eikonalAdvectionDiffusionApproach": "true",
                "$ELECTRO_MODEL_COEFFS.stimulusLocationMin": "(0 0 0)",
                "$ELECTRO_MODEL_COEFFS.stimulusLocationMax": "(0.01 0.01 0.01)",
                "$ELECTRO_MODEL_COEFFS.c0": "60",
                # ionicHeterogeneity block for eikonalECG blend mode, namedRegions with its regions.
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.field": "uvc_transmural",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.mode": "namedRegions",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.endocardialCells.range": "(0 0.3)",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.mCells.range": "(0.3 0.7)",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.regions.epicardialCells.range": "(0.7 1)",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionWidth": "0.1",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.transitionMode": "blend",
                "$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.smoothing": "smoothstep",
            },
        )
        self.assertIn("ionicHeterogeneity", text)
        self.assertIn("transitionMode blend;", text)
        self.assertIn("transitionWidth 0.1;", text)
        self.assertIn("smoothing smoothstep;", text)
        self.assertIn("field uvc_transmural;", text)


class TestRestitutionEikonalSolver1D(unittest.TestCase):
    """applicable_when keys naming a real driver_path resolve ``$SCOPE.`` and ``<name>`` before matching."""

    _NETWORK_NAME = "purkinjeNetwork"
    _COUPLING_NAME = "pvj"

    @classmethod
    def _overrides(cls, conduction_system_solver: str) -> dict[str, str]:
        purkinje = (
            f"$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.{cls._NETWORK_NAME}"
            ".purkinjeGraphModelCoeffs"
        )
        coupling = (
            f"$ELECTRO_MODEL_COEFFS.domainCouplings.{cls._COUPLING_NAME}"
        )
        return {
            f"$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.{cls._NETWORK_NAME}"
            ".conductionSystemDomain": "purkinjeGraphModel",
            f"{purkinje}.graphFile": "purkinjeGraph",
            f"{purkinje}.purkinjeCV": "[0 1 -1 0 0 0 0] 2.0",
            f"{purkinje}.vm1DRest": "-0.084",
            f"{purkinje}.rootStimulus.node": "0",
            f"{purkinje}.rootStimulus.startTime": "0.0",
            f"{purkinje}.rootStimulus.duration": "0.0",
            f"{purkinje}.rootStimulus.intensity": "0.0",
            f"{purkinje}.outputVariables.export": "(activationTime)",
            f"{coupling}.conductionNetworkDomain": cls._NETWORK_NAME,
            f"{coupling}.couplingMode": "unidirectional",
            f"{coupling}.electroDomainCoupler": "eikonalMonodomainPvjCoupler",
            # eikonalMonodomainPvjCoupler FatalErrors at construction without rPvj, unlike reactionDiffusionPvjCoupler.
            f"{coupling}.rPvj": "1e5",
            f"{purkinje}.conductionSystemSolver": conduction_system_solver,
        }

    def _build(self, conduction_system_solver: str) -> str:
        from omnidriver.cardiacfoam.dict_builder import build_electro_properties

        return build_electro_properties(
            {
                "myocardiumSolver": "monodomainSolver",
                "ionicModel": "BuenoOrovio",
                "tissue": "epicardialCells",
            },
            overrides=self._overrides(conduction_system_solver),
        )

    def test_restitution_specific_keys_appear_in_applicable_entries(self) -> None:
        from omnidriver.cardiacfoam.dict_builder import (
            resolve_context,
            select_applicable_entries,
        )

        context = resolve_context(
            {"myocardiumSolver": "monodomainSolver", "ionicModel": "BuenoOrovio",
             "tissue": "epicardialCells"},
            overrides=self._overrides("restitutionEikonalSolver1D"),
        )
        paths = {e.driver_path for e in select_applicable_entries(context)}
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>."
            "purkinjeGraphModelCoeffs.useEdgeConductance",
            paths,
        )
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>."
            "purkinjeGraphModelCoeffs.referenceConductance",
            paths,
        )

    def test_restitution_build_emits_solver_specific_keys(self) -> None:
        """The keys are written under the concrete instance name, not the "<name>" template."""
        text = self._build("restitutionEikonalSolver1D")
        self.assertIn("conductionSystemSolver restitutionEikonalSolver1D;", text)
        self.assertIn("useEdgeConductance true;", text)
        self.assertIn("referenceConductance 1.0;", text)

    def test_restitution_build_differs_from_plain_eikonal_by_more_than_the_solver_name(self) -> None:
        restitution_lines = self._build("restitutionEikonalSolver1D").splitlines()
        plain_lines = self._build("eikonalSolver1D").splitlines()

        differing = sum(
            1 for a, b in zip(restitution_lines, plain_lines) if a != b
        )
        self.assertGreater(
            differing, 1,
            "restitutionEikonalSolver1D and eikonalSolver1D builds differ "
            f"by only {differing} line(s) -- restitution-specific keys are "
            "being dropped again",
        )
        restitution_text = "\n".join(restitution_lines)
        plain_text = "\n".join(plain_lines)
        self.assertIn("useEdgeConductance", restitution_text)
        self.assertNotIn("useEdgeConductance", plain_text)
        self.assertIn("referenceConductance", restitution_text)
        self.assertNotIn("referenceConductance", plain_text)

    def test_plain_eikonalSolver1D_does_not_gain_restitution_keys(self) -> None:
        text = self._build("eikonalSolver1D")
        self.assertIn("conductionSystemSolver eikonalSolver1D;", text)
        self.assertNotIn("useEdgeConductance", text)
        self.assertNotIn("referenceConductance", text)


if __name__ == "__main__":
    unittest.main()
