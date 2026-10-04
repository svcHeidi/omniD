from __future__ import annotations
from pathlib import Path
from typing import Callable, Iterable

from omnidriver.core.runtime.models import DataArtifact, TutorialSpec
from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG
from omnidriver.cardiacfoam.detection import (
    detect_ionic_model_name,
    detect_myocardium_solver_name,
    detect_ionic_export_list,
    electro_properties_has_block,
    detect_verification_model_type,
    detect_active_tension_model_name,
    detect_active_tension_export_list,
)

SolverHandler = Callable[[Path, TutorialSpec, "str | None"], tuple[DataArtifact, ...]]

# The solver writes an ionic or active-tension variable only when the case's
# ``outputVariables`` lists it; with no list it exports none.
def _exported_ionic_variables(case_root: Path, ionic_model: str | None) -> tuple[str, ...]:
    properties = case_root / "constant" / "electroProperties"
    declared = detect_ionic_export_list(properties) if properties.exists() else None
    entry = IONIC_MODEL_CATALOG.get(ionic_model) if ionic_model is not None else None
    if declared is None or entry is None:
        return ()
    # The solver filters the requested list before allocating AUTO_WRITE
    # fields (ionicModelIO::exportedFieldNamesRef), so a raw dictionary token
    # is not output evidence: predict only names the selected model can export.
    accepted = {"Vm", *entry.states, *entry.algebraic}
    return tuple(name for name in declared if name in accepted)

def _exported_active_tension_variables(case_root: Path) -> tuple[str, ...]:
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists() or detect_active_tension_model_name(properties) is None:
        return ()
    return detect_active_tension_export_list(properties) or ()

def _instance_indexed_field_artifact(*, solver: str, field_name: str, description: str) -> DataArtifact:
    artifact_id = f"{solver}_{field_name.lower()}_series"
    produced_by = {
        "monodomain": "monodomainSolver",
        "bidomain": "bidomainSolver",
        "eikonal": "eikonalSolver",
        "single_cell": "singleCellSolver",
    }[solver]
    return DataArtifact(
        artifact_id=artifact_id,
        path_pattern=f"{{instance}}/{field_name}",
        format="openfoam_time_dirs",
        variables=(field_name,),
        description=description,
        produced_by=produced_by,
        instance_indexed=True,
    )

def _predict_single_cell(case_root: Path, spec: TutorialSpec, ionic_model: str | None) -> tuple[DataArtifact, ...]:
    if ionic_model is None:
        return ()
    return (
        DataArtifact(
            artifact_id="single_cell_trace",
            path_pattern="postProcessing/*.txt",
            format="csv_sweep",
            variables=_exported_ionic_variables(case_root, ionic_model) + _exported_active_tension_variables(case_root),
            description=f"Per-case time series produced by singleCellSolver (ionicModel={ionic_model})",
            produced_by="singleCellSolver",
            instance_indexed=False,
        ),
    )

def _predict_monodomain(case_root: Path, spec: TutorialSpec, ionic_model: str | None) -> tuple[DataArtifact, ...]:
    if ionic_model is None:
        return ()
    artifacts: list[DataArtifact] = []
    artifacts.append(_instance_indexed_field_artifact(
        solver="monodomain",
        field_name="Vm",
        description=f"Membrane voltage Vm (monodomainSolver, ionicModel={ionic_model})",
    ))
    for var in _exported_ionic_variables(case_root, ionic_model):
        if var == "Vm":
            continue
        artifacts.append(_instance_indexed_field_artifact(
            solver="monodomain",
            field_name=var,
            description=f"Ionic export {var} (monodomainSolver)",
        ))
    return tuple(artifacts)

def _predict_bidomain(case_root: Path, spec: TutorialSpec, ionic_model: str | None) -> tuple[DataArtifact, ...]:
    if ionic_model is None:
        return ()
    artifacts: list[DataArtifact] = []
    for field_name, description in (
        ("Vm", f"Membrane voltage Vm (bidomainSolver, ionicModel={ionic_model})"),
        ("phiE", "Extracellular potential phiE (bidomainSolver)"),
        ("phiI", "Intracellular potential phiI (bidomainSolver)"),
    ):
        artifacts.append(_instance_indexed_field_artifact(
            solver="bidomain",
            field_name=field_name,
            description=description,
        ))
    for var in _exported_ionic_variables(case_root, ionic_model):
        if var == "Vm":
            continue
        artifacts.append(_instance_indexed_field_artifact(
            solver="bidomain",
            field_name=var,
            description=f"Ionic export {var} (bidomainSolver)",
        ))
    return tuple(artifacts)

def _predict_eikonal(case_root: Path, spec: TutorialSpec, ionic_model: str | None) -> tuple[DataArtifact, ...]:
    return (
        _instance_indexed_field_artifact(
            solver="eikonal",
            field_name="activationTime",
            description="Activation time (eikonalSolver)",
        ),
    )

def _predict_ecg(case_root: Path) -> tuple[DataArtifact, ...]:
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists():
        return ()
    if not electro_properties_has_block(properties, "ecgDomains"):
        return ()
    text = properties.read_text()
    artifacts: list[DataArtifact] = []
    if "pseudoECG" in text:
        artifacts.append(DataArtifact(
            artifact_id="ecg_pseudo_ecg",
            path_pattern="postProcessing/pseudoECG.dat",
            format="csv_probe",
            description="Pseudo-ECG time series at the declared electrodes",
            produced_by="pseudoECG",
            instance_indexed=False,
        ))
    if "torsoECG" in text:
        artifacts.append(DataArtifact(
            artifact_id="ecg_torso_ecg",
            path_pattern="postProcessing/torsoECG.dat",
            format="csv_probe",
            description="Torso-ECG time series at the declared electrodes",
            produced_by="torsoECG",
            instance_indexed=False,
        ))
    return tuple(artifacts)

def _predict_purkinje(case_root: Path) -> tuple[DataArtifact, ...]:
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists():
        return ()
    if not electro_properties_has_block(properties, "conductionNetworkDomains"):
        return ()
    return (
        DataArtifact(
            artifact_id="purkinje_network_time_series",
            path_pattern="postProcessing/purkinjeNetwork.dat",
            format="csv_probe",
            description="Purkinje network time-series — node Vm, activation times, PVJ coupling currents (one row per writeInterval)",
            produced_by="conductionSystemDomain",
            instance_indexed=False,
        ),
        DataArtifact(
            artifact_id="purkinje_network_vtk_series",
            path_pattern="postProcessing/purkinjeNetworkVTK/purkinjeNetwork_*.vtk",
            format="vtk_sequence",
            description="Per-timestep Purkinje network VTK — one file per write step named purkinjeNetwork_<6-digit-timeIndex>.vtk",
            produced_by="conductionSystemDomain",
            instance_indexed=False,
        ),
    )

def _predict_verification(case_root: Path) -> tuple[DataArtifact, ...]:
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists():
        return ()
    verifier_type = detect_verification_model_type(properties)
    if verifier_type is None:
        return ()
    return (
        DataArtifact(
            artifact_id="verification_error_summary",
            # Every non-Eikonal verifier writes "<...>_<N>_cells.dat" with nothing
            # after "cells" but the extension:
            #   3D_19_cells.dat                   (manufacturedFDAMonodomainVerifier)
            #   rotatedAnisotropy_3D_19_cells.dat (manufacturedAnisotropicMonodomainVerifier)
            #   bathBidomain_3D_19_cells.dat      (manufacturedFDABathBidomainVerifier)
            #   <dimension>_19_cells.dat          (manufacturedFDABidomainVerifier)
            path_pattern="postProcessing/manufactured*Summary*.dat" if "Eikonal" in verifier_type else "postProcessing/*_cells.dat",
            format="csv_probe",
            description=f"Manufactured-solution L1/L2/Linf error norms emitted by {verifier_type}",
            produced_by=verifier_type,
            instance_indexed=False,
        ),
    )

def _predict_active_tension(case_root: Path, solver: str) -> tuple[DataArtifact, ...]:
    if solver == "singleCellSolver":
        return ()
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists():
        return ()
    at_model = detect_active_tension_model_name(properties)
    if at_model is None:
        return ()
    variables = _exported_active_tension_variables(case_root)
    return tuple(
        DataArtifact(
            artifact_id=f"active_tension_{var}_series",
            path_pattern=f"{{instance}}/{var}",
            format="openfoam_time_dirs",
            variables=(var,),
            description=f"Active tension {var} (activeTensionModel={at_model})",
            produced_by="sequentialElectroMechanical",
            instance_indexed=True,
        )
        for var in variables
    )

_SOLVER_HANDLERS: dict[str, SolverHandler] = {
    "singleCellSolver": _predict_single_cell,
    "monodomainSolver": _predict_monodomain,
    "bidomainSolver": _predict_bidomain,
    "eikonalSolver": _predict_eikonal,
}

def _read_solver_and_ionic(case_root: Path) -> tuple[str, str | None] | None:
    properties = case_root / "constant" / "electroProperties"
    if not properties.exists():
        return None
    try:
        solver = detect_myocardium_solver_name(properties)
    except KeyError:
        return None
    try:
        ionic = detect_ionic_model_name(properties)
    except KeyError:
        ionic = None
    return solver, ionic

def predict_cardiac_artifacts(case_root: Path, spec: TutorialSpec) -> tuple[DataArtifact, ...]:
    read = _read_solver_and_ionic(case_root)
    if read is None:
        return ()
    solver, ionic_model = read
    handler = _SOLVER_HANDLERS.get(solver)
    solver_derived = handler(case_root, spec, ionic_model) if handler is not None else ()
    return (
        solver_derived
        + _predict_ecg(case_root)
        + _predict_purkinje(case_root)
        + _predict_verification(case_root)
        + _predict_active_tension(case_root, solver)
    )
