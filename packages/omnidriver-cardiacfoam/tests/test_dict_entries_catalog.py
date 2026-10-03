from __future__ import annotations

import tempfile
import typing
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.dict_entries import all_documented_driver_paths
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.active_tension_catalog import ACTIVE_TENSION_MODEL_CATALOG
from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from cardiacfoam_assertions import assert_foam_entry

# Two adapters are installed side by side, so there is no ambient default.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:dict_entries_catalog")

VALID_PHASES = {"anatomy", "physics", "stimulus", "solver"}


class TestDictEntryCatalog(unittest.TestCase):
    def test_catalog_contains_core_physics_and_electro_paths(self) -> None:
        physics_paths = {entry.driver_path for entry in PHYSICS_PROPERTY_ENTRIES}
        self.assertEqual(physics_paths, {"type"})

        documented = set(all_documented_driver_paths(_CTX))
        expected = {
            "myocardiumSolver",
            "$ELECTRO_MODEL_COEFFS.solutionAlgorithm",
            "$ELECTRO_MODEL_COEFFS.ionicModel",
            "$ELECTRO_MODEL_COEFFS.tissue",
            "$ELECTRO_MODEL_COEFFS.dimension",
            "$ELECTRO_MODEL_COEFFS.writeAfterTime",
            "$ELECTRO_MODEL_COEFFS.utilities",
            "$ELECTRO_MODEL_COEFFS.initSampleCell",
            "$ELECTRO_MODEL_COEFFS.outputVariables.ionic.export",
            "$ELECTRO_MODEL_COEFFS.outputVariables.activeTension.export",
            "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1",
            "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusIntensity",
            "$ELECTRO_MODEL_COEFFS.eikonalAdvectionDiffusionApproach",
            "$ELECTRO_MODEL_COEFFS.bathPotentialDomain.bathCellZones",
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver",
            "$ELECTRO_MODEL_COEFFS.activeTensionModel",
            "$ELECTRO_MODEL_COEFFS.couplingSignal",
        }
        self.assertTrue(expected.issubset(documented))

    def test_catalog_paths_are_unique(self) -> None:
        documented = all_documented_driver_paths(_CTX)
        self.assertEqual(len(documented), len(set(documented)))

    def test_catalog_exposes_gui_value_hints_for_key_entries(self) -> None:
        type_entry = PHYSICS_PROPERTY_ENTRIES[0]
        self.assertEqual(type_entry.value_kind, "enum")
        self.assertIn("electroMechanicalModel", type_entry.enum_values)

        monodomain_entries = {
            entry.driver_path: entry for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["monodomain"]
        }
        self.assertEqual(
            monodomain_entries["$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusLocationMin"].value_kind,
            "vector3",
        )
        self.assertEqual(
            monodomain_entries["$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusIntensity"].value_kind,
            "dimensioned_scalar",
        )

        ecg_entries = {entry.driver_path: entry for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["ecg"]}
        self.assertTrue(
            ecg_entries[
                "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.electrodePositions.<electrode>"
            ].dynamic_path
        )

        active_tension = {
            entry.driver_path: entry
            for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["active_tension"]
        }
        self.assertIn(
            "LandNiedererTWorld",
            active_tension["$ELECTRO_MODEL_COEFFS.activeTensionModel"].enum_values,
        )
        self.assertIn(
            "LandNiedererTWorldBatched",
            active_tension["$ELECTRO_MODEL_COEFFS.activeTensionModel"].enum_values,
        )
        self.assertEqual(
            set(active_tension["$ELECTRO_MODEL_COEFFS.activeTensionModel"].enum_values),
            set(ACTIVE_TENSION_MODEL_CATALOG),
        )
        self.assertEqual(
            active_tension["$ELECTRO_MODEL_COEFFS.couplingSignal"].enum_values,
            ("Vm", "vm"),
        )


class TestConductionSystemSchemaContract(unittest.TestCase):
    """Verifies that the conduction_system group uses the keys the C++ code actually reads."""

    def setUp(self):
        self.entries = {
            e.driver_path: e
            for e in ELECTRO_PROPERTY_ENTRY_GROUPS["conduction_system"]
        }

    def test_conduction_domain_selector_key_is_conductionSystemDomain(self):
        # C++ uses lowercase key names in dictionary lookups.
        matching = [
            p for p in self.entries
            if p.endswith(".conductionSystemDomain")
        ]
        self.assertTrue(
            len(matching) >= 1,
            "Expected at least one entry whose path ends with '.conductionSystemDomain'"
        )

    def test_graph_file_schema_is_documented_on_the_coeffs_subdict(self):
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.graphFile",
            self.entries,
        )
        self.assertNotIn(
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.pvjNodes",
            self.entries,
        )
        self.assertNotIn(
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.pvjLocations",
            self.entries,
        )

    def test_root_stimulus_sub_entries_documented(self):
        for sub in ("startTime", "startTimeList", "duration", "intensity", "node"):
            matching = [
                p
                for p in self.entries
                if p.endswith(f".purkinjeGraphModelCoeffs.rootStimulus.{sub}")
            ]
            self.assertTrue(
                len(matching) >= 1,
                f"rootStimulus.{sub} not documented"
            )

    def test_root_stimulus_start_time_list_matches_solver_fallback_semantics(self):
        prefix = (
            "$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>."
            "purkinjeGraphModelCoeffs.rootStimulus."
        )
        start_time = self.entries[prefix + "startTime"]
        start_time_list = self.entries[prefix + "startTimeList"]

        self.assertEqual(start_time.value_kind, "scalar")
        self.assertEqual(start_time_list.value_kind, "scalar_list")
        self.assertEqual(start_time.unit, "s")
        self.assertEqual(start_time_list.unit, "s")
        self.assertIn(
            "src/electroModels/electroDomains/conductionSystemDomain/"
            "conductionSystemDomain.C",
            start_time_list.source_refs,
        )
        self.assertIn("fallback", start_time.notes)
        self.assertIn("takes precedence", start_time_list.description)

    def test_root_stimulus_start_time_list_source_fixture_parses(self):
        fixture = Path(__file__).with_name("fixtures") / "root_stimulus_start_time_list.foam"
        assert_foam_entry(
            fixture,
            "startTimeList",
            "(0.01 0.3)",
            scope=("purkinjeGraphModelCoeffs", "rootStimulus"),
        )

    def test_personalized_templates_schema_and_source_fixture(self):
        ecg_entries = {
            entry.driver_path: entry
            for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["ecg"]
        }
        prefix = (
            "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.personalizedTemplates."
        )
        expected = {
            "ionicModelConfig.ionicModel",
            "ionicModelConfig.tissue",
            "ionicModelConfig.solver",
            "ionicModelConfig.absTol",
            "ionicModelConfig.relTol",
            "ionicModelConfig.batchedSubsteps",
            "ionicModelConfig.singleCellStimulus.stim_start",
            "ionicModelConfig.singleCellStimulus.stim_period_S1",
            "ionicModelConfig.singleCellStimulus.stim_duration",
            "ionicModelConfig.singleCellStimulus.stim_amplitude",
            "ionicModelConfig.singleCellStimulus.nstim1",
            "ionicModelConfig.singleCellStimulus.nstim2",
            "nBeats", "duration", "dt",
        }
        self.assertTrue({prefix + leaf for leaf in expected}.issubset(ecg_entries))
        self.assertEqual(ecg_entries[prefix + "duration"].unit, "s")
        self.assertEqual(
            ecg_entries[prefix + "ionicModelConfig.singleCellStimulus.stim_period_S1"].unit,
            "ms",
        )
        fixture = Path(__file__).with_name("fixtures") / "eikonal_ecg_personalized_templates.foam"
        assert_foam_entry(
            fixture, "ionicModel", "TWorldcompactBatched",
            scope=("eikonalSolverCoeffs", "ecgDomains", "ECG", "personalizedTemplates", "ionicModelConfig"),
        )
        assert_foam_entry(
            fixture, "nBeats", "10",
            scope=("eikonalSolverCoeffs", "ecgDomains", "ECG", "personalizedTemplates"),
        )

    def test_nested_ecg_verification_model_is_a_supported_source_alias(self):
        entries = {
            entry.driver_path: entry
            for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["ecg"]
        }
        prefix = "$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.verificationModel."
        for leaf in ("type", "enabled", "dimension", "referenceQuadratureOrder", "checkQuadratureOrders"):
            self.assertIn(prefix + leaf, entries)
        self.assertEqual(
            entries[prefix + "type"].enum_values,
            (
                "manufacturedPseudoECGVerifier",
                "manufacturedEikonalECGVerifier",
            ),
        )
        self.assertNotIn(prefix + "alpha", entries)
        self.assertNotIn(prefix + "k", entries)

    def test_purkinjeGraphModelCoeffs_chi_and_cm_documented(self):
        chi_keys = [p for p in self.entries if p.endswith(".purkinjeGraphModelCoeffs.chi")]
        cm_keys  = [p for p in self.entries if p.endswith(".purkinjeGraphModelCoeffs.cm")]
        self.assertTrue(len(chi_keys) >= 1, "purkinjeGraphModelCoeffs.chi not documented")
        self.assertTrue(len(cm_keys)  >= 1, "purkinjeGraphModelCoeffs.cm not documented")

class TestDomainCouplingSchemaContract(unittest.TestCase):
    """Verifies that the domain_couplings group owns the domainCouplings schema."""

    def setUp(self):
        self.entries = {
            e.driver_path: e
            for e in ELECTRO_PROPERTY_ENTRY_GROUPS["domain_couplings"]
        }

    def test_coupler_selector_key_is_electroDomainCoupler(self):
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.electroDomainCoupler",
            self.entries,
        )

    def test_coupling_helper_keys_documented(self):
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.conductionNetworkDomain",
            self.entries,
        )
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.rPvj",
            self.entries,
        )
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.pvjRadius",
            self.entries,
        )
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.pvjCouplingScheme",
            self.entries,
        )
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.domainCouplings.<name>.couplingMode",
            self.entries,
        )

    def test_common_model_coeffs_owns_electrophysics_advance_scheme(self):
        common_entries = {
            e.driver_path: e
            for e in ELECTRO_PROPERTY_ENTRY_GROUPS["common_model_coeffs"]
        }
        self.assertIn(
            "$ELECTRO_MODEL_COEFFS.electrophysicsAdvanceScheme",
            common_entries,
        )
        self.assertEqual(
            common_entries["$ELECTRO_MODEL_COEFFS.electrophysicsAdvanceScheme"].enum_values,
            ("staggeredElectrophysicsAdvanceScheme",),
        )


def test_existing_entries_in_catalog_have_empty_defaults() -> None:
    """Structured-constraint fields default empty; adopting them is opt-in per entry."""
    all_entries = list(PHYSICS_PROPERTY_ENTRIES)
    for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
        all_entries.extend(group)
    assert len(all_entries) > 80
    for entry in all_entries:
        assert isinstance(entry.applicable_when, dict)
        assert isinstance(entry.forbidden_when, dict)
        assert isinstance(entry.required_when, dict)
        assert isinstance(entry.mutually_exclusive_with, tuple)


class TestElectroPropertiesPresenceScans(unittest.TestCase):
    """Presence helpers used by the predictor's domain-aware handlers."""

    def _write(self, body: str) -> Path:
        import tempfile
        from pathlib import Path
        temp = tempfile.mkdtemp()
        path = Path(temp) / "electroProperties"
        path.write_text(body)
        return path

    def test_has_block_finds_top_level_block(self) -> None:
        from omnidriver.cardiacfoam.detection import electro_properties_has_block
        path = self._write(
            "myocardiumSolver bidomainSolver;\n"
            "bidomainSolverCoeffs\n{\n  ionicModel TNNP;\n}\n"
            "ecgDomains\n{\n  myECG { ecgSolver pseudoECG; }\n}\n"
        )
        self.assertTrue(electro_properties_has_block(path, "ecgDomains"))
        self.assertFalse(electro_properties_has_block(path, "conductionNetworkDomains"))

    def test_has_block_handles_inline_brace(self) -> None:
        from omnidriver.cardiacfoam.detection import electro_properties_has_block
        path = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "conductionNetworkDomains { purk { } }\n"
        )
        self.assertTrue(
            electro_properties_has_block(path, "conductionNetworkDomains")
        )

    def test_has_block_ignores_substring_matches(self) -> None:
        from omnidriver.cardiacfoam.detection import electro_properties_has_block
        path = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n  ecgDomainsCount 0;\n}\n"
        )
        self.assertFalse(electro_properties_has_block(path, "ecgDomains"))

    def test_detect_verification_model_type_present(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_verification_model_type
        path = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n"
            "  ionicModel monodomainFDAManufactured;\n"
            "  verificationModel\n  {\n"
            "    type manufacturedFDAMonodomainVerifier;\n"
            "  }\n"
            "}\n"
        )
        self.assertEqual(
            detect_verification_model_type(path),
            "manufacturedFDAMonodomainVerifier",
        )

    def test_detect_verification_model_type_absent_returns_none(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_verification_model_type
        path = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n  ionicModel TNNP;\n}\n"
        )
        self.assertIsNone(detect_verification_model_type(path))


class TestDetectActiveTensionModelName(unittest.TestCase):
    def _write(self, text: str) -> Path:
        p = Path(tempfile.mkdtemp()) / "electroProperties"
        p.write_text(text)
        return p

    def test_detects_nash_panfilov(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_active_tension_model_name
        props = self._write(
            "myocardiumSolver singleCellSolver;\n"
            "singleCellSolverCoeffs\n{\n"
            "    activeTensionModel NashPanfilov;\n"
            "}\n"
        )
        self.assertEqual(detect_active_tension_model_name(props), "NashPanfilov")

    def test_detects_goktepe_kuhl(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_active_tension_model_name
        props = self._write(
            "myocardiumSolver singleCellSolver;\n"
            "singleCellSolverCoeffs\n{\n"
            "    activeTensionModel GoktepeKuhl;\n"
            "}\n"
        )
        self.assertEqual(detect_active_tension_model_name(props), "GoktepeKuhl")

    def test_returns_none_when_block_absent(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_active_tension_model_name
        props = self._write(
            "myocardiumSolver singleCellSolver;\n"
            "singleCellSolverCoeffs\n{\n"
            "    ionicModel TNNP;\n"
            "}\n"
        )
        self.assertIsNone(detect_active_tension_model_name(props))


class TestDetectActiveTensionExportList(unittest.TestCase):
    def _write(self, text: str) -> Path:
        p = Path(tempfile.mkdtemp()) / "electroProperties"
        p.write_text(text)
        return p

    def test_detects_ta_export(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_active_tension_export_list
        props = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n"
            "    outputVariables\n    {\n"
            "        activeTension\n        {\n"
            "            export ( Ta );\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(detect_active_tension_export_list(props), ("Ta",))

    def test_returns_none_when_absent(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_active_tension_export_list
        props = self._write(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n"
            "    ionicModel TNNP;\n"
            "}\n"
        )
        self.assertIsNone(detect_active_tension_export_list(props))


class TestEmptyExportListIsKnownEmpty(unittest.TestCase):
    """An explicit ``export ()`` is known and empty; ``None`` means no ``export`` block."""

    def _case_root(self, text: str) -> Path:
        case_root = Path(tempfile.mkdtemp())
        constant = case_root / "constant"
        constant.mkdir()
        (constant / "electroProperties").write_text(text)
        return case_root

    def _electro_properties(
        self,
        *,
        ionic_export: str,
        ionic_model: str = "AlievPanfilov",
        at_export: str | None = None,
    ) -> str:
        at_block = ""
        if at_export is not None:
            at_block = (
                "        activeTension\n        {\n"
                f"            export ( {at_export} );\n"
                "        }\n"
            )
        return (
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n"
            f"    ionicModel {ionic_model};\n"
            "    outputVariables\n    {\n"
            "        ionic\n        {\n"
            f"            export ( {ionic_export} );\n"
            "        }\n"
            f"{at_block}"
            "    }\n"
            "}\n"
        )

    def test_empty_ionic_export_detects_as_empty_tuple_not_none(self) -> None:
        from omnidriver.cardiacfoam.detection import detect_ionic_export_list

        case_root = self._case_root(self._electro_properties(ionic_export=""))
        declared = detect_ionic_export_list(case_root / "constant" / "electroProperties")
        self.assertIsNotNone(declared, "empty export () must not be reported as unknown")
        self.assertEqual(declared, ())

    def test_empty_active_tension_export_detects_as_empty_tuple_not_none(self) -> None:
        from omnidriver.cardiacfoam.detection import (
            detect_active_tension_export_list,
        )

        case_root = self._case_root(
            self._electro_properties(ionic_export="Vm", at_export="")
        )
        declared = detect_active_tension_export_list(
            case_root / "constant" / "electroProperties"
        )
        self.assertIsNotNone(declared, "empty export () must not be reported as unknown")
        self.assertEqual(declared, ())

    def test_predictor_honours_empty_export_over_catalog_defaults(self) -> None:
        from omnidriver.cardiacfoam.artifacts_predictor import (
            _exported_ionic_variables,
        )
        from omnidriver.cardiacfoam.ionic_model_catalog import (
            IONIC_MODEL_CATALOG,
        )

        # The catalog must actually recommend something, or this test would
        # pass for the wrong reason.
        self.assertTrue(IONIC_MODEL_CATALOG["AlievPanfilov"].recommended_exports)

        empty = self._case_root(self._electro_properties(ionic_export=""))
        self.assertEqual(_exported_ionic_variables(empty, "AlievPanfilov"), ())

    def test_predictor_still_falls_back_when_export_block_absent(self) -> None:
        from omnidriver.cardiacfoam.artifacts_predictor import (
            _exported_ionic_variables,
        )
        from omnidriver.cardiacfoam.ionic_model_catalog import (
            IONIC_MODEL_CATALOG,
        )

        case_root = self._case_root(
            "myocardiumSolver monodomainSolver;\n"
            "monodomainSolverCoeffs\n{\n"
            "    ionicModel AlievPanfilov;\n"
            "}\n"
        )
        self.assertEqual(
            _exported_ionic_variables(case_root, "AlievPanfilov"),
            IONIC_MODEL_CATALOG["AlievPanfilov"].recommended_exports,
        )

    def test_predictor_export_filter_matches_every_ionic_catalog_entry(self) -> None:
        """The catalog, not a tutorial result, defines exportable field names."""
        from omnidriver.cardiacfoam.artifacts_predictor import (
            _exported_ionic_variables,
            _predict_monodomain,
        )
        from omnidriver.cardiacfoam.ionic_model_catalog import (
            IONIC_MODEL_CATALOG,
        )

        unsupported = "notAnIonicCatalogSymbol"
        for model_name, entry in IONIC_MODEL_CATALOG.items():
            supported = next(iter(entry.states + entry.algebraic))
            self.assertNotIn(unsupported, entry.states + entry.algebraic)
            case_root = self._case_root(
                self._electro_properties(
                    ionic_model=model_name,
                    ionic_export=f"Vm {supported} {unsupported}",
                )
            )

            self.assertEqual(
                _exported_ionic_variables(case_root, model_name),
                ("Vm", supported),
                model_name,
            )
            predicted = _predict_monodomain(case_root, None, model_name)
            self.assertEqual(
                [artifact.artifact_id for artifact in predicted],
                ["monodomain_vm_series", f"monodomain_{supported.lower()}_series"],
                model_name,
            )


class TestControlDictEntries(unittest.TestCase):
    """CONTROL_DICT_ENTRIES catalog shape contract."""

    def test_catalog_exposes_delta_t_and_end_time(self) -> None:
        from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES
        driver_paths = {e.driver_path for e in CONTROL_DICT_ENTRIES}
        self.assertIn("deltaT", driver_paths)
        self.assertIn("endTime", driver_paths)

    def test_time_entries_carry_seconds_unit(self) -> None:
        from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES
        time_entries = {"deltaT", "endTime", "startTime", "writeInterval"}
        for entry in CONTROL_DICT_ENTRIES:
            if entry.driver_path in time_entries:
                self.assertTrue(
                    entry.unit.startswith("s"),
                    f"{entry.driver_path} must carry a seconds unit, got '{entry.unit}'"
                )

    def test_entries_belong_to_solver_phase(self) -> None:
        from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES
        for entry in CONTROL_DICT_ENTRIES:
            self.assertIn("solver", entry.phases,
                          f"{entry.driver_path} must be in solver phase")

    def test_entries_are_marked_required(self) -> None:
        from omnidriver.cardiacfoam.common_dict_entries import CONTROL_DICT_ENTRIES
        for entry in CONTROL_DICT_ENTRIES:
            self.assertTrue(entry.required,
                            f"{entry.driver_path} must be required=True")


if __name__ == "__main__":
    unittest.main()


def _all_entries():
    yield from PHYSICS_PROPERTY_ENTRIES
    for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
        yield from group


def test_every_dict_entry_has_at_least_one_phase():
    unclassified = [e for e in _all_entries() if not e.phases]
    assert not unclassified, (
        f"{len(unclassified)} entries have no phases: "
        + ", ".join(e.driver_path for e in unclassified[:10])
    )


def test_every_phase_value_is_a_valid_literal():
    invalid = []
    for e in _all_entries():
        bad = [p for p in e.phases if p not in VALID_PHASES]
        if bad:
            invalid.append((e.driver_path, bad))
    assert not invalid, f"invalid phases: {invalid}"
