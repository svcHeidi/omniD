"""Supplied inputs for native openCARP tests, and the conformance target
table. Nothing here is discovered: the tutorials tree comes from
OMNIDRIVER_OPENCARP_TUTORIALS, and the binary from the ambient PATH and
DYLD_LIBRARY_PATH."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from omnidriver.conformance import (
    ConformanceTarget, QuantityTarget, RecordRun, NativeEnvironmentError, record_run, record_sweep, supplied_tree,
)
from omnidriver.core.quantities import load_point_reference
from omnidriver.opencarp.lat_reader import LAT_FORMAT

NIEDERER_RELPATH = "02_EP_tissue/03E_study_resolution"
LAT_PATH = "out/init_acts_vm_act-thresh.dat"
REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"


def opencarp_tutorials_root() -> Path:
    return supplied_tree("OMNIDRIVER_OPENCARP_TUTORIALS", contains=f"{NIEDERER_RELPATH}/nversion.par")


def require_opencarp_binary() -> None:
    binary = shutil.which("openCARP")
    if binary is None:
        raise NativeEnvironmentError("openCARP is not on PATH")
    proc = subprocess.run([binary, "-buildinfo"], capture_output=True, text=True)
    if "GIT tag" not in proc.stdout:
        raise NativeEnvironmentError(
            "openCARP cannot start (on macOS, set DYLD_LIBRARY_PATH to the directory "
            "holding libsundials_cvode; evidence A4-A6): " + proc.stderr[-400:]
        )


def niederer_sweep(tmp_path: Path, *, dx_values: tuple[float, ...], tend: float,
                   extra: Mapping[str, Any] | None = None, tolerate_missing: tuple[str, ...] = ()) -> Path:
    """``niedererNVersion`` over ``dx_values`` (dt 50 us), through ``omnidriver sweep-run``."""
    require_opencarp_binary()
    return record_sweep(
        tmp_path, plugin="opencarp", record="niedererNVersion", cases_root=opencarp_tutorials_root(),
        sweep={"dx": dx_values}, study={"nversion.par:tend": tend, "nversion.par:dt": 50.0, **(extra or {})},
        tolerate_missing=tolerate_missing, timeout_s=600,
    )


def niederer_run(tmp_path: Path, *, dx: float, tend: float, extra: Mapping[str, Any] | None = None,
                 tolerate_missing: tuple[str, ...] = ()) -> RecordRun:
    require_opencarp_binary()
    return record_run(
        tmp_path, plugin="opencarp", record="niedererNVersion", cases_root=opencarp_tutorials_root(),
        sweep={"dx": (dx,)}, study={"nversion.par:tend": tend, "nversion.par:dt": 50.0, **(extra or {})},
        tolerate_missing=tolerate_missing, timeout_s=600,
    )


def require_opencarp_mpi_launcher() -> None:
    """The ``mpirun`` first on PATH starts one MPI world of openCARP processes
    (docs/solver-learning/opencarp.md), checked up front so a wrong environment
    fails naming the fix, not as a failed case whose preflight message stayed
    in its child process."""
    from omnidriver.opencarp.parallel import launcher_diagnostics

    require_opencarp_binary()
    dag = {"steps": [{"id": "solve", "command": "mpirun", "args": ["-np", "2", "openCARP"]}]}
    problems = [d.message for d in launcher_diagnostics(dag, os.environ)]
    if shutil.which("mpirun") is None:
        problems.append("no mpirun on PATH")
    if problems:
        raise NativeEnvironmentError(
            "the parallel openCARP tests need the launcher of the MPI openCARP was built against "
            "first on PATH (for a bundled-MPICH install, <openCARP prefix>/lib/petsc/bin) and, "
            "where the host name does not resolve, HYDRA_IFACE=lo0: " + "; ".join(problems)
        )


# Coarse and short, so the native tier stays seconds long. The quantity runs
# at dx 500 um to 150 ms so that all nine points activate; N = 2 differs from
# serial only in the last digit the LAT file prints (six decimals), a
# five-thousandth of dt.
TARGETS: dict[str, dict[str, Any]] = {
    "niedererNVersion": dict(
        base_study={"dx": 1000.0, "nversion.par:tend": 10.0, "nversion.par:dt": 50.0},
        patch=("nversion.par:gregion[0].g_il", 0.2),
        untouched=("nversion.par", ("gregion[0]", "g_it")),
        sweep_name="dx",
        sweep_values=(1000.0, 500.0),
        unknown_name="nversion.par:gregion[0].g_ill",
    ),
}


def conformance_target(record: str, tmp_path: Path) -> ConformanceTarget:
    require_opencarp_mpi_launcher()
    reference = load_point_reference(REFERENCE)
    at = {label: point.coordinates for label, point in reference.points.items() if point.coordinates is not None}
    return ConformanceTarget(
        plugin="opencarp", record=record, cases_root=opencarp_tutorials_root(), scratch_root=tmp_path / "scratch",
        quantity=QuantityTarget(
            artifact_format=LAT_FORMAT, reference=REFERENCE, pairs={label: label for label in at}, at=at,
            at_unit=reference.length_unit, max_sampling_offset=0.001,
            study={"dx": 500.0, "nversion.par:tend": 150.0, "nversion.par:dt": 50.0},
            sweep_values=(500.0, 250.0), tolerance=5.0, tolerance_unit="ms", parallel_tolerance=1e-5,
        ),
        **TARGETS[record],
    )
