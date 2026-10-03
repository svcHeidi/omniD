"""What the cardiacFOAM stack predicts a case will write: the artifacts each solver, export list,
ECG, Purkinje, verification and active-tension block declare, and the utility steps of a DAG."""
from __future__ import annotations

import fnmatch
import tempfile
import unittest
from pathlib import Path

from omnidriver.cardiacfoam.artifacts_predictor import _predict_verification
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.artifacts import predict_data_artifacts as _predict
from omnidriver.core.runtime.models import (
    DataArtifact,
    TutorialSpec,
)


def predict_data_artifacts(case_root, spec):
    """What the stack predicts beyond the driver's own state and log records."""
    predicted = _predict(case_root, spec, driver_context=load_plugin_context("cardiacfoam"))
    return tuple(a for a in predicted if a.produced_by != "omnidriver")


def _make_spec(
    case_root: Path,
    *,
    expected_artifacts: tuple[DataArtifact, ...] = (),
) -> TutorialSpec:
    metadata: dict[str, object] = {
        "setup_root": str(case_root),
        "output_dir": str(case_root / "output"),
    }
    if expected_artifacts:
        metadata["expected_artifacts"] = expected_artifacts
    return TutorialSpec(
        name="fixture",
        case_root=case_root,
        metadata=metadata,
    )


def _write_single_cell_electro_properties(
    case_root: Path,
    *,
    ionic_model: str = "AlievPanfilov",
    tissue: str = "myocyte",
) -> None:
    """Synthesize the minimum-viable single-cell electroProperties."""
    constant = case_root / "constant"
    constant.mkdir(parents=True, exist_ok=True)
    (constant / "electroProperties").write_text(
        "myocardiumSolver singleCellSolver;\n"
        "singleCellSolverCoeffs\n"
        "{\n"
        f"    ionicModel    {ionic_model};\n"
        f"    tissue        {tissue};\n"
        "    solutionAlgorithm explicit;\n"
        "}\n"
    )


class TestPredictorSingleCell(unittest.TestCase):
    def test_emits_artifact_with_variables_from_catalog(self) -> None:
        """AlievPanfilov advertises states ('u', 'recovery_r') in the ionic model catalog — the predictor must source variables from there rather than redefining them locally."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_single_cell_electro_properties(
                case_root, ionic_model="AlievPanfilov"
            )
            spec = _make_spec(case_root)

            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertEqual(trace.produced_by, "singleCellSolver")
            self.assertEqual(
                trace.path_pattern,
                "postProcessing/*.txt",
            )
            self.assertIn("u", trace.variables)
            self.assertIn("recovery_r", trace.variables)

    def test_variables_change_with_ionic_model(self) -> None:
        """Convergence guard: the predictor must return different variables for different ionic models."""
        with tempfile.TemporaryDirectory() as temp_a, tempfile.TemporaryDirectory() as temp_b:
            case_a = Path(temp_a) / "case"
            case_b = Path(temp_b) / "case"
            case_a.mkdir()
            case_b.mkdir()
            _write_single_cell_electro_properties(case_a, ionic_model="TNNP")
            _write_single_cell_electro_properties(case_b, ionic_model="AlievPanfilov")

            artifacts_tnnp = predict_data_artifacts(case_a, _make_spec(case_a))
            artifacts_ap = predict_data_artifacts(case_b, _make_spec(case_b))

            trace_tnnp = next(a for a in artifacts_tnnp if a.artifact_id == "single_cell_trace")
            trace_ap = next(a for a in artifacts_ap if a.artifact_id == "single_cell_trace")

            self.assertNotEqual(
                set(trace_tnnp.variables), set(trace_ap.variables),
                "predictor returned identical variables for two different "
                "ionic models — catalog consultation is broken",
            )
            # TNNP.recommended_exports references a calcium variable;
            # AlievPanfilov has no calcium.
            self.assertIn("calcium_Cai", trace_tnnp.variables)


    def test_unknown_ionic_model_returns_only_vm_and_empty_trace(self) -> None:
        """The predictor must not raise on a model name absent from the catalog — agents may mutate dicts to an as-yet-undefined model."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_single_cell_electro_properties(
                case_root, ionic_model="NotARealModel"
            )
            spec = _make_spec(case_root)

            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("single_cell_trace", ids)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertEqual(trace.variables, ())


class TestPredictorMergesStaticOverride(unittest.TestCase):
    def test_static_expected_artifacts_passed_through(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_single_cell_electro_properties(case_root)
            static = DataArtifact(
                artifact_id="exact_error_norm",
                path_pattern="postProcessing/exact_error.json",
                format="json_summary",
                description="L2 error vs analytic solution",
            )
            spec = _make_spec(case_root, expected_artifacts=(static,))

            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("exact_error_norm", ids)

    def test_static_wins_on_artifact_id_collision(self) -> None:
        """spec.metadata['expected_artifacts'] is the authoring escape hatch."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_single_cell_electro_properties(case_root)

            # Discover what the derived artifact_ids are, then collide on one.
            derived = predict_data_artifacts(case_root, _make_spec(case_root))
            self.assertGreater(len(derived), 0)
            colliding_id = derived[0].artifact_id

            static = DataArtifact(
                artifact_id=colliding_id,
                path_pattern="custom/path",
                format="csv_probe",
                description="hand-authored override",
            )
            spec = _make_spec(case_root, expected_artifacts=(static,))

            artifacts = predict_data_artifacts(case_root, spec)
            by_id = {a.artifact_id: a for a in artifacts}
            self.assertEqual(by_id[colliding_id].description, "hand-authored override")
            self.assertEqual(by_id[colliding_id].path_pattern, "custom/path")


def _write_pde_electro_properties(
    case_root: Path,
    *,
    solver: str,
    ionic_model: str = "TNNP",
    export_list: tuple[str, ...] | None = None,
) -> None:
    """Synthesize a monodomain/bidomain electroProperties shell."""
    (case_root / "constant").mkdir(parents=True, exist_ok=True)
    body = (
        f"myocardiumSolver  {solver};\n"
        f"{solver}Coeffs\n"
        "{\n"
        f"    ionicModel    {ionic_model};\n"
        "    solutionAlgorithm implicit;\n"
    )
    if export_list is not None:
        body += (
            "    outputVariables\n"
            "    {\n"
            "        ionic\n"
            "        {\n"
            f"            export ({' '.join(export_list)});\n"
            "        }\n"
            "    }\n"
        )
    body += "}\n"
    (case_root / "constant" / "electroProperties").write_text(body)


def _write_eikonal_electro_properties(case_root: Path) -> None:
    """Eikonal cases do not declare an ionicModel (constraint enforced by dict_entries.py); the predictor must not require one."""
    (case_root / "constant").mkdir(parents=True, exist_ok=True)
    (case_root / "constant" / "electroProperties").write_text(
        "myocardiumSolver eikonalSolver;\n"
        "eikonalSolverCoeffs\n"
        "{\n"
        "    conductivity (1 0 0  0 1 0  0 0 1);\n"
        "}\n"
    )


class TestPredictorMonodomain(unittest.TestCase):
    def test_emits_time_series_with_catalog_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="TNNP"
            )
            spec = _make_spec(case_root)

            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("monodomain_vm_series", ids)
            self.assertIn("monodomain_calcium_cai_series", ids)
            for a in artifacts:
                self.assertTrue(a.instance_indexed, f"{a.artifact_id} not time-indexed")
                self.assertEqual(a.produced_by, "monodomainSolver")
                self.assertEqual(a.format, "openfoam_time_dirs")

    def test_pattern_uses_time_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="AlievPanfilov"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            for a in artifacts:
                self.assertTrue(
                    a.path_pattern.startswith("{instance}/"),
                    f"{a.artifact_id}: {a.path_pattern}",
                )


class TestPredictorBidomain(unittest.TestCase):
    def test_emits_phi_e_and_phi_i_in_variables(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="bidomainSolver", ionic_model="TNNP"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("bidomain_vm_series", ids)
            self.assertIn("bidomain_phie_series", ids)
            self.assertIn("bidomain_phii_series", ids)
            self.assertIn("bidomain_calcium_cai_series", ids)
            for a in artifacts:
                self.assertEqual(a.produced_by, "bidomainSolver")
                self.assertTrue(a.path_pattern.startswith("{instance}/"))


class TestPredictorEikonal(unittest.TestCase):
    def test_emits_activationTime_field(self) -> None:
        """Eikonal cases do not declare ionicModel — the predictor must produce exactly activationTime per-variable artifacts."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_eikonal_electro_properties(case_root)
            spec = _make_spec(case_root)

            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertEqual(ids, {"eikonal_activationtime_series"})
            for a in artifacts:
                self.assertEqual(a.produced_by, "eikonalSolver")
                self.assertTrue(a.path_pattern.startswith("{instance}/"))


class TestPredictorExportListFiltering(unittest.TestCase):
    """Predictor must report what will actually be on disk, not the catalog superset."""

    def test_export_list_overrides_catalog_states_for_monodomain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root,
                solver="monodomainSolver",
                ionic_model="monodomainFDAManufactured",
                export_list=("u1", "u2", "u3"),
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            # Per-variable: Vm always + each declared export.
            self.assertIn("monodomain_vm_series", ids)
            self.assertIn("monodomain_u1_series", ids)
            self.assertIn("monodomain_u2_series", ids)
            self.assertIn("monodomain_u3_series", ids)

    def test_export_list_overrides_catalog_states_for_bidomain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root,
                solver="bidomainSolver",
                ionic_model="TNNP",
                export_list=("V", "Ca_i"),
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("bidomain_vm_series", ids)
            self.assertIn("bidomain_phie_series", ids)
            self.assertIn("bidomain_phii_series", ids)
            self.assertIn("bidomain_v_series", ids)
            self.assertIn("bidomain_ca_i_series", ids)

    def test_export_list_overrides_catalog_for_single_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir()
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver singleCellSolver;\n"
                "singleCellSolverCoeffs\n"
                "{\n"
                "    ionicModel    AlievPanfilov;\n"
                "    outputVariables\n"
                "    {\n"
                "        ionic\n"
                "        {\n"
                "            export (Vm u notAState);\n"
                "        }\n"
                "    }\n"
                "}\n"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            # A token the model cannot export is no output evidence (ionicModelIO::exportedFieldNamesRef).
            self.assertEqual(trace.variables, ("Vm", "u"))

    def test_missing_export_list_falls_back_to_recommended_exports(self) -> None:
        """AlievPanfilov.recommended_exports = ('u', 'recovery_r') in ionic_model_catalog.py."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_single_cell_electro_properties(
                case_root, ionic_model="AlievPanfilov"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertEqual(trace.variables, ("u", "recovery_r"))

    def test_explicitly_empty_export_list_predicts_zero_ionic_exports(self) -> None:
        """``outputVariables.ionic.export ( );`` is a real, deliberate declaration -- the solver will write no ionic fields at all."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root,
                solver="monodomainSolver",
                ionic_model="TNNP",
                export_list=(),
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            # Vm is always predicted for monodomain; no per-ionic-variable
            # artifact should appear since the declared export list is empty.
            self.assertIn("monodomain_vm_series", ids)
            self.assertFalse(
                {a.artifact_id for a in artifacts if a.artifact_id != "monodomain_vm_series"},
                f"expected zero ionic-export artifacts beyond Vm, got {ids - {'monodomain_vm_series'}}",
            )


class TestPredictorManufacturedFdaRoundTrip(unittest.TestCase):
    """A verification tutorial declares analytic-error artifacts statically while the predictor still derives the field series."""

    def test_both_derived_and_static_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root,
                solver="monodomainSolver",
                ionic_model="monodomainFDAManufactured",
            )
            error_norm = DataArtifact(
                artifact_id="exact_error_norm",
                path_pattern="postProcessing/exact_error.json",
                format="json_summary",
                description="L2 error vs analytic manufactured solution",
                produced_by="manufacturedFDAMonodomainVerifier",
            )
            spec = _make_spec(case_root, expected_artifacts=(error_norm,))

            artifacts = predict_data_artifacts(case_root, spec)
            derived_ids = {a.artifact_id for a in artifacts}
            # Derived: per-variable artifacts named with the monodomain_ prefix.
            self.assertTrue(
                any(i.startswith("monodomain_") for i in derived_ids),
                f"expected at least one monodomain_* derived artifact, got: {derived_ids}",
            )
            self.assertIn("exact_error_norm", derived_ids)


class TestPredictorGracefulFallback(unittest.TestCase):
    def test_missing_electro_properties_returns_only_static(self) -> None:
        """Before a run mutates the case, electroProperties may not yet exist (or live under setup/)."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            static = DataArtifact(
                artifact_id="placeholder",
                path_pattern="postProcessing/placeholder.csv",
                format="csv_probe",
            )
            spec = _make_spec(case_root, expected_artifacts=(static,))

            artifacts = predict_data_artifacts(case_root, spec)
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].artifact_id, "placeholder")

    def test_unknown_solver_returns_only_static(self) -> None:
        """Unhandled solvers (e.g., a future addition) must not error."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir()
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver totallyMadeUpSolver;\n"
                "totallyMadeUpSolverCoeffs { }\n"
            )
            spec = _make_spec(case_root)

            artifacts = predict_data_artifacts(case_root, spec)
            self.assertEqual(artifacts, ())


class TestPredictorECG(unittest.TestCase):
    """When ecgDomains is declared in electroProperties, the predictor must add an ECG time-series artifact pointing at the writer's output file (`postProcessing/{pseudoECG,torsoECG}.dat`)."""

    def test_pseudo_ecg_is_predicted_when_block_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir(parents=True, exist_ok=True)
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver bidomainSolver;\n"
                "bidomainSolverCoeffs\n{\n"
                "    ionicModel TNNP;\n"
                "}\n"
                "ecgDomains\n{\n"
                "    myECG\n    {\n"
                "        ecgSolver pseudoECG;\n"
                "    }\n"
                "}\n"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("ecg_pseudo_ecg", ids)
            ecg = next(a for a in artifacts if a.artifact_id == "ecg_pseudo_ecg")
            self.assertEqual(ecg.path_pattern, "postProcessing/pseudoECG.dat")
            self.assertEqual(ecg.format, "csv_probe")

    def test_torso_ecg_is_predicted_when_block_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir(parents=True, exist_ok=True)
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver bidomainSolver;\n"
                "bidomainSolverCoeffs\n{\n"
                "    ionicModel TNNP;\n"
                "}\n"
                "ecgDomains\n{\n"
                "    myECG\n    {\n"
                "        ecgSolver torsoECG;\n"
                "    }\n"
                "}\n"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("ecg_torso_ecg", ids)

    def test_no_ecg_when_block_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="bidomainSolver", ionic_model="TNNP",
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertNotIn("ecg_pseudo_ecg", ids)
            self.assertNotIn("ecg_torso_ecg", ids)


class TestPredictorPurkinje(unittest.TestCase):
    """When conductionNetworkDomains is declared, the predictor must add the Purkinje time-series and VTK series artifacts."""

    def test_purkinje_artifacts_emitted_when_block_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir(parents=True, exist_ok=True)
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver monodomainSolver;\n"
                "monodomainSolverCoeffs\n{\n"
                "    ionicModel TNNP;\n"
                "}\n"
                "conductionNetworkDomains\n{\n"
                "    purk\n    {\n"
                "        purkinjeGraphModelCoeffs\n        {\n"
                "            conductionSystemSolver monodomain1DSolver;\n"
                "            graphFile purkinjeGraph;\n"
                "        }\n"
                "    }\n"
                "}\n"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("purkinje_network_time_series", ids)
            self.assertIn("purkinje_network_vtk_series", ids)
            vtk = next(
                a for a in artifacts
                if a.artifact_id == "purkinje_network_vtk_series"
            )
            self.assertEqual(
                vtk.path_pattern,
                "postProcessing/purkinjeNetworkVTK/purkinjeNetwork_*.vtk",
            )

    def test_no_purkinje_when_block_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="TNNP",
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertNotIn("purkinje_network_time_series", ids)
            self.assertNotIn("purkinje_network_vtk_series", ids)


class TestPredictorVerification(unittest.TestCase):
    """When verificationModel.type is declared, predict the verifier's error-summary .dat output."""

    def test_manufactured_monodomain_pseudo_ecg_verifier_is_predicted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            (case_root / "constant").mkdir(parents=True, exist_ok=True)
            (case_root / "constant" / "electroProperties").write_text(
                "myocardiumSolver monodomainSolver;\n"
                "monodomainSolverCoeffs\n{\n"
                "    ionicModel monodomainFDAManufactured;\n"
                "    verificationModel\n    {\n"
                "        type manufacturedFDAMonodomainVerifier;\n"
                "    }\n"
                "}\n"
            )
            spec = _make_spec(case_root)
            artifacts = predict_data_artifacts(case_root, spec)
            ids = {a.artifact_id for a in artifacts}
            self.assertIn("verification_error_summary", ids)
            verify = next(
                a for a in artifacts
                if a.artifact_id == "verification_error_summary"
            )
            self.assertTrue(
                verify.path_pattern.startswith("postProcessing/")
                and verify.path_pattern.endswith(".dat"),
                verify.path_pattern,
            )
            self.assertIn("*", verify.path_pattern)

    def test_no_verification_when_block_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="TNNP",
            )
            spec = _make_spec(case_root)
            ids = {a.artifact_id for a in predict_data_artifacts(case_root, spec)}
            self.assertNotIn("verification_error_summary", ids)


class TestPredictorComposesUtilityProduces(unittest.TestCase):
    """When a spec's workflow_dag declares utility steps, the predictor merges every matching utility's `produces` entries into its output."""

    def test_workflow_dag_utility_step_contributes_produces(self) -> None:
        """A monodomain spec whose workflow_dag includes `setTorsoOrganConductivityField` (a real utility) must carry that utility's produces entries in the predicted set."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root,
                solver="monodomainSolver",
                ionic_model="TNNP",
            )
            spec = _make_spec(case_root)
            # Inject a workflow_dag step naming a real utility from
            # UTILITY_CATALOG. setTorsoOrganConductivityField declares produces.
            spec_with_dag = TutorialSpec(
                name=spec.name,
                case_root=spec.case_root,
                metadata={
                    "setup_root": spec.metadata["setup_root"],
                    "output_dir": spec.metadata["output_dir"],
                    "workflow_dag": {
                        "steps": [
                            {"id": "solve", "command": "cardiacFoam",
                             "depends_on": []},
                            {"id": "setConductivity",
                             "command": "setTorsoOrganConductivityField",
                             "depends_on": ["solve"]},
                        ],
                    },
                },
            )

            artifacts = predict_data_artifacts(case_root, spec_with_dag)
            ids = {a.artifact_id for a in artifacts}
            # The setTorsoOrganConductivityField manifest declares produces
            # entries — at least one should appear. The exact artifact_id
            # depends on the manifest; produced_by is stable.
            produced_by_utility = [
                a for a in artifacts
                if a.produced_by == "setTorsoOrganConductivityField"
            ]
            self.assertGreater(
                len(produced_by_utility), 0,
                f"expected at least one produces entry from "
                f"setTorsoOrganConductivityField; got ids: {ids}",
            )

    def test_unknown_utility_in_dag_is_silently_skipped(self) -> None:
        """If workflow_dag mentions a command that isn't in UTILITY_CATALOG (e.g. `blockMesh`, which is an OpenFOAM built-in, not a cardiacFoam utility), the predictor proceeds without error."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="TNNP",
            )
            base = _make_spec(case_root)
            spec_with_dag = TutorialSpec(
                name=base.name,
                case_root=base.case_root,
                metadata={
                    "setup_root": base.metadata["setup_root"],
                    "output_dir": base.metadata["output_dir"],
                    "workflow_dag": {
                        "steps": [
                            {"id": "mesh", "command": "blockMesh",
                             "depends_on": []},
                        ],
                    },
                },
            )
            # Must not raise — predictor returns whatever the solver
            # handler produced, without any blockMesh contribution.
            artifacts = predict_data_artifacts(case_root, spec_with_dag)
            self.assertGreater(len(artifacts), 0)
            produced_by_blockmesh = [
                a for a in artifacts if a.produced_by == "blockMesh"
            ]
            self.assertEqual(produced_by_blockmesh, [])

    def test_no_workflow_dag_means_no_utility_artifacts(self) -> None:
        """Specs without workflow_dag (minimal) still work; the utility composition is a no-op."""
        with tempfile.TemporaryDirectory() as temp:
            case_root = Path(temp) / "case"
            case_root.mkdir()
            _write_pde_electro_properties(
                case_root, solver="monodomainSolver", ionic_model="TNNP",
            )
            spec = _make_spec(case_root)  # _make_spec gives no workflow_dag
            artifacts = predict_data_artifacts(case_root, spec)
            # All artifacts must be from the solver handler, none from
            # a utility.
            for a in artifacts:
                self.assertNotIn(
                    a.produced_by, ("setTorsoOrganConductivityField",
                                    "sweepCurrents", "ionicHeterogeneityProbe"),
                )


class TestPredictorActiveTension(unittest.TestCase):
    """_predict_active_tension fires for singleCellSolver+AT cases and is suppressed when no activeTensionModel entry is present."""

    def _write_single_cell_with_at(self, tmp: Path, *, at_model: str, exports: str) -> None:
        ep = tmp / "constant" / "electroProperties"
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text(
            f"myocardiumSolver singleCellSolver;\n"
            f"singleCellSolverCoeffs\n{{\n"
            f"    ionicModel TNNP;\n"
            f"    activeTensionModel {at_model};\n"
            f"    outputVariables\n    {{\n"
            f"        activeTension\n        {{\n"
            f"            export ( {exports} );\n"
            f"        }}\n"
            f"    }}\n"
            f"}}\n"
        )

    def test_ta_artifact_included_in_single_cell_trace_for_nash_panfilov(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_single_cell_with_at(tmp, at_model="NashPanfilov", exports="Ta")
            spec = _make_spec(tmp)
            artifacts = predict_data_artifacts(tmp, spec)
            ids = [a.artifact_id for a in artifacts]
            self.assertNotIn("active_tension_Ta_series", ids)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertIn("Ta", trace.variables)

    def test_ta_artifact_included_in_single_cell_trace_for_goktepe_kuhl(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_single_cell_with_at(tmp, at_model="GoktepeKuhl", exports="Ta")
            spec = _make_spec(tmp)
            artifacts = predict_data_artifacts(tmp, spec)
            ids = [a.artifact_id for a in artifacts]
            self.assertNotIn("active_tension_Ta_series", ids)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertIn("Ta", trace.variables)

    def test_no_at_artifacts_when_block_absent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            ep = tmp / "constant" / "electroProperties"
            ep.parent.mkdir(parents=True, exist_ok=True)
            ep.write_text(
                "myocardiumSolver monodomainSolver;\n"
                "monodomainSolverCoeffs\n{\n"
                "    ionicModel TNNP;\n"
                "}\n"
            )
            spec = _make_spec(tmp)
            artifacts = predict_data_artifacts(tmp, spec)
            ids = [a.artifact_id for a in artifacts]
            self.assertFalse(any("active_tension" in i for i in ids))

    def test_at_artifact_uses_declared_export_list(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_single_cell_with_at(tmp, at_model="NashPanfilov", exports="Ta")
            spec = _make_spec(tmp)
            artifacts = predict_data_artifacts(tmp, spec)
            at_artifacts = [a for a in artifacts if "active_tension" in a.artifact_id]
            self.assertEqual(len(at_artifacts), 0)
            trace = next(a for a in artifacts if a.artifact_id == "single_cell_trace")
            self.assertIn("Ta", trace.variables)

    def test_at_artifact_format_is_openfoam_time_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # Use bidomain instead of singleCellSolver to test the time_dirs output format
            ep = tmp / "constant" / "electroProperties"
            ep.parent.mkdir(parents=True, exist_ok=True)
            ep.write_text(
                "myocardiumSolver bidomainSolver;\n"
                "bidomainSolverCoeffs\n{\n"
                "    ionicModel TNNP;\n"
                "    activeTensionModel NashPanfilov;\n"
                "    outputVariables { activeTension { export ( Ta ); } }\n"
                "}\n"
            )
            spec = _make_spec(tmp)
            artifacts = predict_data_artifacts(tmp, spec)
            ta = next(a for a in artifacts if a.artifact_id == "active_tension_Ta_series")
            self.assertEqual(ta.format, "openfoam_time_dirs")
            self.assertTrue(ta.instance_indexed)


if __name__ == "__main__":
    unittest.main()

def _electro_properties(
    tmp_path: Path, *, myocardium_solver: str, verifier_type: str
) -> Path:
    path = tmp_path / "constant" / "electroProperties"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""FoamFile
{{
    version 2.0;
    format ascii;
    class dictionary;
    object electroProperties;
}}
myocardiumSolver {myocardium_solver};
{myocardium_solver}Coeffs
{{
    verificationModel
    {{
        type {verifier_type};
    }}
}}
"""
    )
    return path


# Every non-Eikonal manufactured verifier's OFstream writes "<...>_<N>_cells.dat",
# with no token between "cells" and the extension; the bath verifier writes no
# "bathBidomain_" prefix.
_CASES = (
    ("monodomainSolver", "manufacturedFDAMonodomainVerifier", "3D_19_cells.dat"),
    (
        "monodomainSolver",
        "manufacturedAnisotropicMonodomainVerifier",
        "rotatedAnisotropy_3D_19_cells.dat",
    ),
    ("bidomainSolver", "manufacturedFDABidomainVerifier", "3D_19_cells.dat"),
    (
        "bidomainSolver",
        "manufacturedFDABathBidomainVerifier",
        "3D_19_cells.dat",
    ),
)


def test_verification_artifact_pattern_matches_every_real_verifier_filename(tmp_path):
    for index, (myocardium_solver, verifier_type, real_filename) in enumerate(_CASES):
        case_root = tmp_path / f"case{index}"
        _electro_properties(
            case_root, myocardium_solver=myocardium_solver, verifier_type=verifier_type
        )

        artifacts = _predict_verification(case_root)
        assert len(artifacts) == 1
        pattern = artifacts[0].path_pattern

        assert fnmatch.fnmatch(f"postProcessing/{real_filename}", pattern), (
            f"{verifier_type}: pattern {pattern!r} does not match real "
            f"filename {real_filename!r}"
        )
        assert not fnmatch.fnmatch(
            f"postProcessing/{real_filename}", "postProcessing/*_*_cells_*.dat"
        )


def test_eikonal_verification_artifact_pattern_is_unaffected(tmp_path):
    case_root = tmp_path / "eikonal"
    _electro_properties(
        case_root,
        myocardium_solver="eikonalSolver",
        verifier_type="manufacturedEikonalECGVerifier",
    )

    artifacts = _predict_verification(case_root)
    assert artifacts[0].path_pattern == "postProcessing/manufactured*Summary*.dat"
