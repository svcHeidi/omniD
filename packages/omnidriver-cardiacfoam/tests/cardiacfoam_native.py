"""Supplied inputs for native cardiacFOAM tests, and the conformance target
table. Not ``conftest``: core's conftest wins ``from conftest import``.
Nothing is discovered: the tree and the sourced OpenFOAM shell are supplied.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT
from omnidriver.conformance import (
    ConformanceTarget, QuantityTarget, RecordRun, record_run, require_commands, supplied_tree,
)

RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
NIEDERER_2011_RELPATH = "NiedererEtAl2011verification"
REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"

#: The reference frame has its origin at P1, the stimulus corner, with a along the 20 mm fibre edge,
#: b along the 7 mm edge and c along the 3 mm edge, so x = a, y = c, z = 7 - b (mm) in cardiacFOAM's
#: frame. Native probe -> (its configured location in cardiacFOAM's frame, m; the reference label;
#: that label's reference coordinates, mm). ``system/Niedererpoints`` is the drift gate.
PROBES = {
    "0": ((0.0, 0.0, 0.007), "P1", (0, 0, 0)),
    "1": ((0.0, 0.0, 0.0), "P2", (0, 7, 0)),
    "2": ((0.019999, 0.0, 0.007), "P3", (20, 0, 0)),
    "3": ((0.019999, 0.0, 0.0), "P4", (20, 7, 0)),
    "4": ((0.0, 0.003, 0.007), "P5", (0, 0, 3)),
    "5": ((0.0, 0.003, 0.0), "P6", (0, 7, 3)),
    "6": ((0.019999, 0.003, 0.007), "P7", (20, 0, 3)),
    "7": ((0.019999, 0.003, 0.0), "P8", (20, 7, 3)),
    "8": ((0.01, 0.0015, 0.0035), "P9", (10, 3.5, 1.5)),
}


def native_tutorials_root() -> Path:
    return supplied_tree("OMNIDRIVER_NATIVE_TUTORIALS")


def niederer_run(tmp_path: Path, *, dx: float, end_time: float | None = None) -> RecordRun:
    require_commands("blockMesh", "cardiacFoam")
    study = {"system/controlDict:endTime": end_time} if end_time is not None else {}
    return record_run(
        tmp_path, plugin="cardiacfoam", record="niederer2011", cases_root=native_tutorials_root(),
        sweep={"dx": (dx,)}, study=study,
    )


_CABLE_CONDUCTIVITY = {
    "value": [2.3, 0.0, 0.0, 2.3, 0.0, 2.3],
    "dimensions": [-1, -3, 3, 0, 0, 2, 0],
}
_COMMANDS = ("blockMesh", "cardiacFoam")

# One row per record, each cut short so a real run takes seconds. A `patch` is a catalogued key the
# native case sets to something else; `untouched` is a sibling it must leave alone; `unknown_name`
# is a typo of a real key. `requires` are the commands the record's pipeline runs.
TARGETS: dict[str, dict[str, Any]] = {
    "manufacturedEikonalECG": dict(
        # Coarsest study resolution (numberCells 10); a real run takes ~13 s.
        requires=_COMMANDS,
        base_study={"numberCells": 10},
        # A catalogued boolean key the native case sets `false` by default.
        patch=("constant/electroProperties:eikonalSolverCoeffs.verificationModel.writeErrorField", True),
        untouched=("constant/electroProperties", ("eikonalSolverCoeffs", "eikonalAdvectionDiffusionApproach")),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:eikonalSolverCoeffs.verificationModel.writeErrorFiel",
    ),
    "singleCell": dict(
        # endTime 0.05 s, not the native 2 s (2e6 steps, ~25 s per real run).
        requires=_COMMANDS,
        base_study={"system/controlDict:endTime": 0.05},
        patch=("constant/electroProperties:singleCellSolverCoeffs.tissue", "epicardialCells"),
        untouched=("constant/electroProperties", ("singleCellSolverCoeffs", "ionicModel")),
        sweep_name="ionicModel",
        # Not BuenoOrovio: the native case's activeTensionModel LandNiedererTWorld needs a Cai
        # signal BuenoOrovio does not supply, fatal at solve time. TNNP and TWorld both supply it.
        sweep_values=("TNNP", "TWorld"),
        unknown_name="constant/electroProperties:singleCellSolverCoeffs.tissu",
    ),
    "restitutionCurves": dict(
        # Coarsest mesh the native blockMeshDict documents (40x6x14); a real run takes seconds.
        requires=_COMMANDS,
        base_study={"blockMeshResolution": [40, 6, 14]},
        patch=("constant/electroProperties:singleCellSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("singleCellSolverCoeffs", "ionicModel")),
        # The two coarsest resolutions the native blockMeshDict documents.
        sweep_name="blockMeshResolution",
        sweep_values=([40, 6, 14], [100, 15, 35]),
        unknown_name="constant/electroProperties:singleCellSolverCoeffs.tissu",
    ),
    "manufacturedBidomain": dict(
        # Hex route, 1D at numberCells 10; a real run takes well under a second.
        requires=_COMMANDS,
        base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10},
        # A scalar manufacturedFDABidomainVerifier reads at 1.0/sqrt(2) when absent.
        patch=("constant/electroProperties:bidomainSolverCoeffs.verificationModel.k", 0.5),
        untouched=("constant/electroProperties", ("bidomainSolverCoeffs", "verificationModel", "type")),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:bidomainSolverCoeffs.verificationModel.q",
    ),
    "manufacturedBathBidomain": dict(
        # Hex route, 1D N=10, endTime 0.02 (36 steps); a real run takes about a second.
        requires=("blockMesh", "topoSet", "setTorsoOrganConductivityField", "cardiacFoam"),
        base_study={"dimension": "1D", "numberCells": 10, "system/controlDict:endTime": 0.02},
        # A catalogued scalar the bath verifier reads (native 0.01).
        patch=("constant/electroProperties:bidomainSolverCoeffs.verificationModel.alpha", 0.02),
        untouched=("constant/electroProperties", ("bidomainSolverCoeffs", "verificationModel", "k")),
        sweep_name="numberCells",
        sweep_values=(10, 20),
        unknown_name="constant/electroProperties:bidomainSolverCoeffs.bathPredictorCorector",
    ),
    "manufacturedMonodomainPseudoECG": dict(
        # Hex route, 3D at numberCells 5 (~4 s real run). 3D, unlike the other manufactured targets:
        # the native default verifier manufacturedAnisotropicMonodomainVerifier is FatalError at any
        # other dimension unless verificationModel.type/anisotropic change too.
        requires=_COMMANDS,
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
    ),
    "cable1DRestitution": dict(
        # dx 1 mm and the smallest legal s1s2SpatialProtocol, so endTime is 1.5 ms. writeInterval is
        # pinned below endTime: ``predict_data_artifacts`` requires one elapsed monodomainSolver
        # field write, which the native 4.25 s never reaches.
        requires=_COMMANDS,
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
    ),
    "cable1DCVConvergence": dict(
        # Mesh + solve only; endTime/writeInterval pinned short as for cable1DRestitution.
        requires=_COMMANDS,
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
    ),
    "manufacturedMonodomain1D3D": dict(
        # Coarsest coupledConvergence point, not the native N=20 (~13 s per run).
        requires=_COMMANDS,
        base_study={
            "numberCells": 10,
            "graphFile": "purkinjeGraph.nodes011",
            "system/controlDict:deltaT": 0.008971136,
        },
        # A catalogued scalar the coupling reads (native default 1.0).
        patch=("constant/electroProperties:monodomainSolverCoeffs.domainCouplings.couplingA.rPvj", 2.0),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="graphFile",
        sweep_values=("purkinjeGraph.nodes011", "purkinjeGraph.nodes021"),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.domainCouplings.couplingA.rPv",
    ),
    "niederer2011": dict(
        # Hex route at the coarsest cartesianConvergence dx (0.5 mm); a few seconds. The quantity
        # runs to 0.15 s so all nine probes activate (P8 at 0.143 s); a decomposed solve differs
        # from the serial one only at the solver tolerance, and probes are written at
        # writePrecision 6, so the parallel tolerance requires equal written values.
        requires=_COMMANDS,
        base_study={"mesh": "hex", "dx": 0.0005, "system/controlDict:endTime": 0.015},
        patch=("constant/electroProperties:monodomainSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("monodomainSolverCoeffs", "ionicModel")),
        sweep_name="dx",
        sweep_values=(0.0005, 0.001),
        unknown_name="constant/electroProperties:monodomainSolverCoeffs.tissu",
        quantity=QuantityTarget(
            artifact_format=ACTIVATION_PROBES_FORMAT, reference=REFERENCE,
            pairs={label: probe for probe, (_, label, _) in PROBES.items()},
            at={probe: at for probe, (at, _, _) in PROBES.items()},
            at_unit="m", max_sampling_offset=0.0,
            study={"dx": 0.0005, "system/controlDict:endTime": 0.15},
            sweep_values=(0.0005, 0.001), tolerance=5.0, tolerance_unit="ms", parallel_tolerance=1e-9,
            parallel_study={"system/decomposeParDict:numberOfSubdomains": 2},
        ),
        # The serial solve of the quantity's run takes about six minutes.
        timeout_s=1500.0,
    ),
}


def conformance_target(record: str, tmp_path: Path) -> ConformanceTarget:
    row = dict(TARGETS[record])
    require_commands(*row.pop("requires"), *(("decomposePar", "reconstructPar", "mpirun") if row.get("quantity") else ()))
    return ConformanceTarget(
        plugin="cardiacfoam", record=record, cases_root=native_tutorials_root(), scratch_root=tmp_path / "scratch", **row,
    )
