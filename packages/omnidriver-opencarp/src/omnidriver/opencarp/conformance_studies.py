"""How ``omnidriver check`` exercises the Niederer N-version record briefly against the real binary: coarse and short.
The quantity runs at dx 500 um to 150 ms so all nine points activate; N = 2 differs from serial only in the last LAT digit (six decimals), a five-thousandth of dt."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.conformance_study import ConformanceStudy, QuantityTarget, RankEvidence
from omnidriver.opencarp.lat_reader import LAT_FORMAT

#: The benchmark C13 and C14 compare against, found under ``--benchmarks``.
REFERENCE = Path("niederer2011.json")

STUDIES: dict[str, ConformanceStudy] = {
    "niedererNVersion": ConformanceStudy(
        requires=("openCARP", "mpirun"),
        base_study={"dx": 1000.0, "nversion.par:tend": 10.0, "nversion.par:dt": 50.0},
        patch=("nversion.par:gregion[0].g_il", 0.2),
        untouched=("nversion.par", ("gregion[0]", "g_it")),
        sweep_name="dx",
        sweep_values=(1000.0, 500.0),
        unknown_name="nversion.par:gregion[0].g_ill",
        quantity=QuantityTarget(
            artifact_format=LAT_FORMAT, reference=REFERENCE, at_unit=None, max_sampling_offset=0.001,
            study={"dx": 500.0, "nversion.par:tend": 150.0, "nversion.par:dt": 50.0},
            sweep_values=(500.0, 250.0), tolerance=5.0, tolerance_unit="ms", parallel_tolerance=1e-5,
            # PETSc prints its world size once, at the end, when asked to log.
            rank_evidence=RankEvidence(log_pattern=r"with (\d+) processors", environment={"PETSC_OPTIONS": "-log_view"}),
        ),
    ),
}
