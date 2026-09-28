"""Supplied inputs for native cardiacFOAM tests, and one conformance target per
tutorial record. Not ``conftest``: core's conftest wins ``from conftest import``.
Nothing is discovered: the tree and the sourced OpenFOAM shell are supplied.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from omnidriver.conformance import ConformanceTarget
from omnidriver.core.runtime.models import DataArtifact, data_artifact_from_json
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from omnidriver.cardiacfoam.records import niederer_2011

RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
NIEDERER_2011_RELPATH = "NiedererEtAl2011verification"


def native_tutorials_root() -> Path:
    """FAILS, never skips, when unset: a native test without the real tree proves nothing."""
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def require_sourced_openfoam(*commands: str) -> None:
    """Fail up front naming the fix, not as C5-C11 verdicts on a plan that could not run."""
    if "WM_PROJECT_DIR" not in os.environ:
        pytest.fail(
            "WM_PROJECT_DIR is not set: run the native cardiacFOAM conformance "
            "tests from a shell that has sourced OpenFOAM, e.g. "
            "`bash -c 'source <OpenFOAM>/etc/bashrc && pytest -m native ...'`"
        )
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        pytest.fail(f"not on PATH in the sourced OpenFOAM shell: {missing}")


def manufactured_eikonal_ecg_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Coarsest study resolution (numberCells 10); a real run takes ~13 s."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedEikonalECG",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"numberCells": 10},
        # A catalogued boolean key the native case sets `false` by default.
        patch=("constant/electroProperties:eikonalSolverCoeffs.verificationModel.writeErrorField", True),
        untouched=("constant/electroProperties", ("eikonalSolverCoeffs", "eikonalAdvectionDiffusionApproach")),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:eikonalSolverCoeffs.verificationModel.writeErrorFiel",
        solver_command="cardiacFoam",
        environment={},
    )


def single_cell_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """endTime 0.05 s, not the native 2 s (2e6 steps, ~25 s per real run)."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="singleCell",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"system/controlDict:endTime": 0.05},
        patch=("constant/electroProperties:singleCellSolverCoeffs.tissue", "epicardialCells"),
        untouched=("constant/electroProperties", ("singleCellSolverCoeffs", "ionicModel")),
        sweep_name="ionicModel",
        # Not BuenoOrovio: the native case's activeTensionModel
        # LandNiedererTWorld needs a Cai signal BuenoOrovio does not supply,
        # fatal at solve time. TNNP and TWorld both supply it.
        sweep_values=("TNNP", "TWorld"),
        unknown_name="constant/electroProperties:singleCellSolverCoeffs.tissu",
        solver_command="cardiacFoam",
        environment={},
    )


def restitution_curves_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Coarsest mesh the native blockMeshDict documents (40x6x14); a real run takes seconds."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="restitutionCurves",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"blockMeshResolution": [40, 6, 14]},
        patch=("constant/electroProperties:singleCellSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("singleCellSolverCoeffs", "ionicModel")),
        # The two coarsest resolutions the native blockMeshDict documents.
        sweep_name="blockMeshResolution",
        sweep_values=([40, 6, 14], [100, 15, 35]),
        unknown_name="constant/electroProperties:singleCellSolverCoeffs.tissu",
        solver_command="cardiacFoam",
        environment={},
    )


def manufactured_bidomain_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Hex route, 1D at numberCells 10; a real run takes well under a second."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedBidomain",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10},
        # A scalar manufacturedFDABidomainVerifier reads at 1.0/sqrt(2) when absent.
        patch=("constant/electroProperties:bidomainSolverCoeffs.verificationModel.k", 0.5),
        untouched=(
            "constant/electroProperties",
            ("bidomainSolverCoeffs", "verificationModel", "type"),
        ),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:bidomainSolverCoeffs.verificationModel.q",
        solver_command="cardiacFoam",
        environment={},
    )


def manufactured_bath_bidomain_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Hex route, 1D N=10, endTime 0.02 (36 steps); a real run takes about a second."""
    require_sourced_openfoam("blockMesh", "topoSet", "setTorsoOrganConductivityField", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedBathBidomain",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"dimension": "1D", "numberCells": 10, "system/controlDict:endTime": 0.02},
        # A catalogued scalar the bath verifier reads (native 0.01).
        patch=("constant/electroProperties:bidomainSolverCoeffs.verificationModel.alpha", 0.02),
        untouched=("constant/electroProperties", ("bidomainSolverCoeffs", "verificationModel", "k")),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:bidomainSolverCoeffs.bathPredictorCorector",
        solver_command="cardiacFoam",
        environment={},
    )


def manufactured_monodomain_pseudo_ecg_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Hex route, 3D at numberCells 5 (~4 s real run)."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedMonodomainPseudoECG",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        # 3D, unlike the other manufactured targets: the native default
        # verifier manufacturedAnisotropicMonodomainVerifier is FatalError at
        # any other dimension unless verificationModel.type/anisotropic change too.
        base_study={"mesh": "hex", "dimension": "3D", "numberCells": 5},
        patch=(
            "constant/electroProperties:monodomainSolverCoeffs.ecgDomains.ECG"
            ".verificationModel.referenceQuadratureOrder",
            48,
        ),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="numberCells",
        sweep_values=(5, 10),
        unknown_name=(
            "constant/electroProperties:monodomainSolverCoeffs.ecgDomains.ECG"
            ".verificationModel.referenceQuadratureOrde"
        ),
        solver_command="cardiacFoam",
        environment={},
    )


_CABLE_CONDUCTIVITY = {
    "value": [2.3, 0.0, 0.0, 2.3, 0.0, 2.3],
    "dimensions": [-1, -3, 3, 0, 0, 2, 0],
}


def cable_1d_restitution_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """dx 1 mm and the smallest legal s1s2SpatialProtocol, so endTime is 1.5 ms.
    writeInterval is pinned below endTime: ``predict_data_artifacts`` requires
    one elapsed monodomainSolver field write, which the native 4.25 s never reaches."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="cable1DRestitution",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={
            "dx": 0.001,
            "system/controlDict:writeInterval": 0.0005,
            "constant/electroProperties:monodomainSolverCoeffs.conductivity": _CABLE_CONDUCTIVITY,
            "s1s2SpatialProtocol": {
                "n_s1": 1, "n_s2": 1, "end_time_buffer_s": 0.0005,
                "requested_di90_ms": 0.0, "reference_repolarization90_s": 0.001,
            },
        },
        patch=("constant/electroProperties:monodomainSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="dx",
        sweep_values=(0.001, 0.0005),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.conductivit",
        solver_command="cardiacFoam",
        environment={},
    )


def cable_1d_cv_convergence_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Mesh + solve only; endTime/writeInterval pinned short as for cable1DRestitution."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="cable1DCVConvergence",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={
            "dx": 0.001,
            "system/controlDict:endTime": 0.0015,
            "system/controlDict:writeInterval": 0.0005,
            "constant/electroProperties:monodomainSolverCoeffs.conductivity": _CABLE_CONDUCTIVITY,
            "constant/electroProperties:monodomainSolverCoeffs.externalStimulus.stimulusStartTimeList": [0.0],
            "constant/electroProperties:monodomainSolverCoeffs.externalStimulus.stimulusLocationMinList": [[0.0, 0.0, 0.0]],
            "constant/electroProperties:monodomainSolverCoeffs.externalStimulus.stimulusLocationMaxList": [[2e-3, 2e-4, 2e-4]],
            "constant/electroProperties:monodomainSolverCoeffs.externalStimulus.stimulusDurationList": [4e-3],
            "constant/electroProperties:monodomainSolverCoeffs.externalStimulus.stimulusIntensityList": [50000.0],
        },
        patch=("constant/electroProperties:monodomainSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="dx",
        sweep_values=(0.001, 0.0005),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.conductivit",
        solver_command="cardiacFoam",
        environment={},
    )


def niederer_sweep(tmp_path: Path, *, dx_values: Sequence[float], end_time: float | None = None,
                    extra: Mapping[str, Any] | None = None) -> Path:
    """Run ``niederer2011`` via ``sweep-run`` at each ``dx`` (metres); returns the output dir."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    base: dict[str, Any] = {
        "entry": "niederer2011", "cases_root": str(native_tutorials_root()),
        **(extra or {}),
    }
    if end_time is not None:
        base["system/controlDict:endTime"] = end_time
    spec = {
        "base": base,
        "sweep": {"mode": "cross_product", "independent": {"dx": list(dx_values)}},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output = tmp_path / "sweep"
    proc = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", "cardiacfoam",
         "--spec", str(spec_path), "--output-dir", str(output),
         "--scratch-dir", str(tmp_path / "scratch")],
        capture_output=True, text=True, timeout=1800,
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        pytest.fail(f"sweep-run printed no JSON (rc={proc.returncode}): {proc.stderr[-2000:]}")
    for case in payload.get("cases", ()):
        if case.get("status") != "completed":
            pytest.fail(f"sweep-run failed (rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}")
    if not payload.get("cases"):
        pytest.fail(f"sweep-run produced no cases (rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}")
    return output


def niederer_run(tmp_path: Path, *, dx: float, end_time: float | None = None) -> tuple[Path, DataArtifact]:
    """Returns ``(case_root, probe)``; ``probe`` is the artifact at ``niederer_2011.POINTS_PATH``."""
    output = niederer_sweep(tmp_path, dx_values=(dx,), end_time=end_time)
    (case,) = build_sweep_context(output).cases
    document = json.loads((output / case.run_document_path).read_text())
    artifact = next(
        data_artifact_from_json(raw) for raw in document["expectedArtifacts"]
        if raw["path_pattern"] == niederer_2011.POINTS_PATH
    )
    return Path(case.case_root), artifact


def manufactured_monodomain_1d3d_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Coarsest coupledConvergence point, not the native N=20 (~13 s per run)."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedMonodomain1D3D",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={
            "numberCells": 10,
            "graphFile": "purkinjeGraph.nodes011",
            "system/controlDict:deltaT": 0.008971136,
        },
        # A catalogued scalar the coupling reads (native default 1.0).
        patch=(
            "constant/electroProperties:monodomainSolverCoeffs"
            ".domainCouplings.couplingA.rPvj",
            2.0,
        ),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="graphFile",
        sweep_values=("purkinjeGraph.nodes011", "purkinjeGraph.nodes021"),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.domainCouplings.couplingA.rPv",
        solver_command="cardiacFoam",
        environment={},
    )


def niederer2011_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Hex route at the coarsest cartesianConvergence dx (0.5 mm); a few seconds."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="niederer2011",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"mesh": "hex", "dx": 0.0005, "system/controlDict:endTime": 0.015},
        patch=("constant/electroProperties:monodomainSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="dx",
        sweep_values=(0.0005, 0.001),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.tissu",
        solver_command="cardiacFoam",
        environment={},
    )
