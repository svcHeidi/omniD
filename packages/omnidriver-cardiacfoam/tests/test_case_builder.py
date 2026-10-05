"""Tests for the dict builder, which synthesizes a complete electroProperties dict from
selectors and overrides and enforces the validator's constraints, so its output is
validator-clean by construction."""
from __future__ import annotations

import unittest

import pytest
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default to discover.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:dict_builder")

class TestDictBuilderModule(unittest.TestCase):
    def test_module_exposes_build_electro_properties(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
        self.assertTrue(callable(build_electro_properties))

    def test_function_accepts_documented_kwargs(self) -> None:
        import inspect
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
        sig = inspect.signature(build_electro_properties)
        params = sig.parameters
        self.assertIn("selectors", params)
        self.assertIn("overrides", params)
        self.assertIn("typical_value_fallback", params)
        self.assertEqual(params["overrides"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(params["typical_value_fallback"].kind, inspect.Parameter.KEYWORD_ONLY)


class TestMinimalSingleCellBuild(unittest.TestCase):
    def test_returns_string_with_foamfile_preamble(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

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
        from omnidriver.cardiacfoam.case_builder import resolve_context
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
        from omnidriver.cardiacfoam.case_builder import resolve_context
        ctx = resolve_context(
            selectors={"myocardiumSolver": "singleCellSolver"},
            overrides=None,
        )
        self.assertEqual(ctx, {"myocardiumSolver": "singleCellSolver"})


class TestApplicableEntrySelection(unittest.TestCase):
    def test_eikonal_context_excludes_ionic_model_entry(self) -> None:
        """ionicModel is forbidden_when under eikonal; the applicable_when-filtered entry is tissue."""
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

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
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import _with_virtual_presence
        from omnidriver.openfoam.case_rules import rule_diagnostics

        return [e.message for e in rule_diagnostics(
            entries, _with_virtual_presence(populated), document="constant/electroProperties",
        )]

    def test_fully_populated_entries_report_nothing(self) -> None:
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.openfoam.case_builder import populate_values
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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

    _MONODOMAIN = {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"}
    _STIMULUS = "$ELECTRO_MODEL_COEFFS.externalStimulus."

    def test_build_refuses_a_stimulus_box_with_no_max_corner(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
        with self.assertRaises(ValueError) as ctx:
            build_electro_properties(
                selectors=self._MONODOMAIN, overrides={self._STIMULUS + "stimulusLocationMin": "(0 0 0)"},
            )
        self.assertIn(
            "one of externalStimulus.stimulusLocationMax, externalStimulus.stimulusLocationMaxList is required",
            str(ctx.exception),
        )

    def test_build_refuses_a_single_min_corner_with_a_max_list(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
        with self.assertRaises(ValueError) as ctx:
            build_electro_properties(
                selectors=self._MONODOMAIN,
                overrides={
                    self._STIMULUS + "stimulusLocationMin": "(0 0 0)",
                    self._STIMULUS + "stimulusLocationMaxList": "((1 1 1))",
                },
            )
        self.assertIn("stimulusLocationMaxList requires externalStimulus.stimulusLocationMinList", str(ctx.exception))

    def test_build_writes_a_stimulus_box_with_both_corners_and_no_block_without_one(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
        text = build_electro_properties(
            selectors=self._MONODOMAIN,
            overrides={
                self._STIMULUS + "stimulusLocationMin": "(0 0 0)", self._STIMULUS + "stimulusLocationMax": "(1 1 1)",
            },
        )
        self.assertIn("stimulusLocationMax (1 1 1);", text)
        self.assertIn("stimulusIntensity", text)
        self.assertNotIn("externalStimulus", build_electro_properties(selectors=self._MONODOMAIN))

    def test_build_raises_on_forbidden_when_violation(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties
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
        from omnidriver.cardiacfoam.case_builder import build_physics_properties
        sig = inspect.signature(build_physics_properties)
        params = sig.parameters
        self.assertIn("selectors", params)
        self.assertIn("overrides", params)
        self.assertIn("typical_value_fallback", params)
        self.assertEqual(params["overrides"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_minimal_electroModel_build(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_physics_properties
        text = build_physics_properties(selectors={"type": "electroModel"})
        self.assertIn("type electroModel;", text)
        self.assertIn("FoamFile", text)
        self.assertIn("object      physicsProperties", text)
        self.assertNotIn("electroProperties", text)
        self.assertNotIn("Coeffs", text)

    def test_missing_required_type_raises(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_physics_properties
        with self.assertRaises(ValueError) as ctx:
            build_physics_properties(selectors={})
        self.assertIn("type", str(ctx.exception))

    def test_invalid_enum_value_raises(self) -> None:
        from omnidriver.cardiacfoam.case_builder import build_physics_properties
        with self.assertRaises(ValueError) as ctx:
            build_physics_properties(selectors={"type": "notARealModel"})
        self.assertIn("notARealModel", str(ctx.exception))


_SINGLE_CELL = {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"}
_MONODOMAIN = {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"}


class TestBuildCase(unittest.TestCase):
    """build_case commits a runnable case and holds it to the pre-run rules."""

    def _build(self, selectors, **kwargs):
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        case_dir = Path(temp.name) / "case"
        return case_dir, build_case(selectors, case_dir=case_dir, driver_context=_CTX, **kwargs)

    def test_writes_every_input_and_an_executable_allrun(self) -> None:
        case_dir, result = self._build(_MONODOMAIN)
        self.assertEqual(result["status"], "ok", result["diagnostics"])
        for name in (
            "constant/electroProperties", "constant/physicsProperties", "system/fvSchemes",
            "system/fvSolution", "system/controlDict", "system/blockMeshDict", "Allrun",
        ):
            self.assertTrue((case_dir / name).is_file(), name)
        self.assertEqual((case_dir / "Allrun").read_text(), "#!/bin/sh\nblockMesh\ncardiacFoam\n")
        self.assertEqual((case_dir / "Allrun").stat().st_mode & 0o777, 0o755)

    def test_a_broken_selector_is_refused_before_anything_is_written(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            build_case(
                {"myocardiumSolver": "eikonalSolver", "ionicModel": "TNNP"}, case_dir=Path(temp) / "case", driver_context=_CTX,
            )
        self.assertFalse((Path(temp) / "case" / "constant").exists())

    def test_an_existing_case_is_replaced_only_with_consent(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            (case_dir / "constant").mkdir(parents=True)
            (case_dir / "constant" / "electroProperties").write_text("# pre-existing\n")
            with self.assertRaises(FileExistsError):
                build_case(_SINGLE_CELL, case_dir=case_dir, driver_context=_CTX)
            build_case(_SINGLE_CELL, case_dir=case_dir, overwrite=True, driver_context=_CTX)
            self.assertIn("myocardiumSolver singleCellSolver;", (case_dir / "constant" / "electroProperties").read_text())

    def test_an_override_no_catalogue_entry_places_is_refused_not_dropped(self) -> None:
        with self.assertRaisesRegex(ValueError, "sealedWallTrace"):
            self._build(_MONODOMAIN, electro_overrides={"$ELECTRO_MODEL_COEFFS.sealedWallTrace": "zeroGradient"})

    def test_single_cell_gets_one_cell_and_refuses_dx(self) -> None:
        case_dir, _ = self._build(_SINGLE_CELL)
        self.assertIn("hex (0 1 2 3 4 5 6 7) (1 1 1)", (case_dir / "system" / "blockMeshDict").read_text())
        with self.assertRaisesRegex(ValueError, "dx"):
            self._build(_SINGLE_CELL, dx=0.0004)

    def test_dx_sizes_the_spatial_mesh(self) -> None:
        from omnidriver.openfoam.case_builder import default_block_mesh_dict_text

        case_dir, _ = self._build(_MONODOMAIN, dx=0.0004)
        self.assertEqual((case_dir / "system" / "blockMeshDict").read_text(), default_block_mesh_dict_text(dx_m=0.0004))

    def test_a_hand_authored_mesh_is_kept(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            (case_dir / "system").mkdir(parents=True)
            (case_dir / "system" / "blockMeshDict").write_text("// custom mesh\n")
            build_case(_MONODOMAIN, case_dir=case_dir, driver_context=_CTX)
            self.assertEqual((case_dir / "system" / "blockMeshDict").read_text(), "// custom mesh\n")

    def test_system_dictionaries_of_an_existing_case_are_kept_unless_overwritten(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            (case_dir / "system").mkdir(parents=True)
            for name in ("controlDict", "fvSchemes", "fvSolution"):
                (case_dir / "system" / name).write_text(f"// mine: {name}\n")
            build_case(_MONODOMAIN, case_dir=case_dir, driver_context=_CTX)
            for name in ("controlDict", "fvSchemes", "fvSolution"):
                self.assertEqual((case_dir / "system" / name).read_text(), f"// mine: {name}\n")
            build_case(_MONODOMAIN, case_dir=case_dir, driver_context=_CTX, overwrite=True)
            self.assertIn("application     cardiacFoam;", (case_dir / "system" / "controlDict").read_text())

    def test_time_step_and_end_time_reach_the_control_dict(self) -> None:
        case_dir, _ = self._build(_SINGLE_CELL, delta_t=0.001, end_time=0.002)
        text = (case_dir / "system" / "controlDict").read_text()
        self.assertIn("deltaT          0.001;", text)
        self.assertIn("endTime         0.002;", text)

    def test_a_time_step_or_end_time_the_controlDict_rules_refuse_writes_nothing(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build_case

        for options, message in (
            ({"delta_t": 0}, "deltaT is 0, outside the catalogue's bounds: must be more than 0."),
            ({"end_time": -1}, "endTime is -1, not after the startTime 0 the built case starts from."),
            ({"end_time": 0}, "endTime is 0, not after the startTime 0 the built case starts from."),
        ):
            with tempfile.TemporaryDirectory() as temp:
                case_dir = Path(temp) / "case"
                with self.assertRaisesRegex(ValueError, message.replace("(", r"\(").replace(")", r"\)")):
                    build_case(_SINGLE_CELL, case_dir=case_dir, driver_context=_CTX, **options)
                self.assertFalse(case_dir.exists())

    def test_a_failed_commit_leaves_no_partial_case(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest import mock
        from omnidriver.cardiacfoam.case_builder import build_case
        from omnidriver.core import case_transaction

        real = case_transaction.atomic_write_bytes
        calls = []

        def die_on_third(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3:
                raise OSError("simulated failure")
            return real(*args, **kwargs)

        with tempfile.TemporaryDirectory() as temp:
            case_dir = Path(temp) / "case"
            with mock.patch.object(case_transaction, "atomic_write_bytes", die_on_third):
                with self.assertRaises(case_transaction.CaseTransactionError):
                    build_case(_SINGLE_CELL, case_dir=case_dir, driver_context=_CTX)
            self.assertFalse((case_dir / "constant" / "electroProperties").exists())

    def test_the_cli_entry_point_splits_the_physics_type_from_the_selectors(self) -> None:
        import tempfile
        from pathlib import Path
        from omnidriver.cardiacfoam.case_builder import build

        with tempfile.TemporaryDirectory() as temp:
            result = build(
                _CTX, Path(temp) / "case", select={**_SINGLE_CELL, "type": "electroModel"},
                set_values={}, options={"endTime": "0.5"}, overwrite=False,
            )
            self.assertEqual(result["status"], "ok", result["diagnostics"])
            with self.assertRaisesRegex(ValueError, "unknown build option"):
                build(_CTX, Path(temp) / "other", select=_SINGLE_CELL, set_values={},
                      options={"mesh": "1"}, overwrite=False)


class TestEikonalECGHeterogeneity(unittest.TestCase):
    """sigmaExtracellular and ionicHeterogeneity entries under eikonalSolver + eikonalECG."""

    def test_sigmaExtracellular_in_catalog_when_ecgDomains_present(self) -> None:
        """Any ecgDomains override sets the virtual ``$ecgDomains_present`` key."""
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import (
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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

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
        from omnidriver.cardiacfoam.case_builder import build_electro_properties

        return build_electro_properties(
            {
                "myocardiumSolver": "monodomainSolver",
                "ionicModel": "BuenoOrovio",
                "tissue": "epicardialCells",
            },
            overrides=self._overrides(conduction_system_solver),
        )

    def test_restitution_specific_keys_appear_in_applicable_entries(self) -> None:
        from omnidriver.cardiacfoam.case_builder import (
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


# A verbatim excerpt of cardiacFOAM src/electroModels/myocardiumModels/bidomainSolver/bidomainSolver.C:
# its constructor.
BIDOMAIN_SOLVER_CXX = Path(__file__).resolve().parent / "fixtures" / "cxx" / "bidomainSolver.C"
_BIDOMAIN = {"myocardiumSolver": "bidomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"}
_SEALED = "$ELECTRO_MODEL_COEFFS.sealedHeartBoundary"
_TRACE = "$ELECTRO_MODEL_COEFFS.sealedWallTrace"


def _native_tree(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "native" / "src" / "electroModels" / "myocardiumModels" / "bidomainSolver"
    source.mkdir(parents=True)
    (source / "bidomainSolver.C").write_text(BIDOMAIN_SOLVER_CXX.read_text())
    (tmp_path / "native" / "tutorials").mkdir()
    monkeypatch.setenv("OMNIDRIVER_NATIVE_TUTORIALS", str(tmp_path / "native" / "tutorials"))


def test_a_key_the_cxx_reads_and_the_catalogue_lacks_is_built_under_its_coeffs_and_noted(tmp_path, monkeypatch) -> None:
    from omnidriver.cardiacfoam.case_builder import build_case

    _native_tree(tmp_path, monkeypatch)
    built = build_case(
        _BIDOMAIN, case_dir=tmp_path / "case", electro_overrides={_SEALED: "yes", _TRACE: "zeroGradient"},
        driver_context=_CTX,
    )
    assert built["status"] == "ok", built["diagnostics"]
    assert [(d["code"], d["field"]) for d in built["diagnostics"]] == [
        ("plugin_catalog_uncatalogued", _SEALED), ("plugin_catalog_uncatalogued", _TRACE),
    ]
    text = (tmp_path / "case" / "constant" / "electroProperties").read_text()
    coeffs = text.split("bidomainSolverCoeffs", 1)[1]
    assert "sealedHeartBoundary yes;" in coeffs


def test_an_override_neither_the_catalogue_nor_the_cxx_places_is_refused_by_name(tmp_path, monkeypatch) -> None:
    from omnidriver.cardiacfoam.case_builder import build_case

    _native_tree(tmp_path, monkeypatch)
    for override, reason in (
        ({"$ELECTRO_MODEL_COEFFS.sealedHeartBoundry": "true"}, "reads no key named 'sealedHeartBoundry'"),
        ({_SEALED: "maybe"}, "read by the C\\+\\+ as Switch"),
    ):
        with pytest.raises(ValueError, match=reason):
            build_case(_BIDOMAIN, case_dir=tmp_path / "case", electro_overrides=override, driver_context=_CTX)
    assert not (tmp_path / "case").exists()


def test_a_build_without_the_cxx_source_says_so_and_refuses_an_uncatalogued_key(tmp_path, monkeypatch) -> None:
    from omnidriver.cardiacfoam.case_builder import build_case

    monkeypatch.delenv("OMNIDRIVER_NATIVE_TUTORIALS", raising=False)
    built = build_case(_BIDOMAIN, case_dir=tmp_path / "case", driver_context=_CTX)
    assert [d["code"] for d in built["diagnostics"]] == ["plugin_cxx_source_not_supplied"]
    with pytest.raises(ValueError, match="C\\+\\+ source is not supplied"):
        build_case(_BIDOMAIN, case_dir=tmp_path / "other", electro_overrides={_SEALED: "true"}, driver_context=_CTX)
