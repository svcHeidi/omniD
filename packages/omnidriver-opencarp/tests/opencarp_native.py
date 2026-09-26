"""Supplied inputs for native openCARP tests. Nothing here is discovered:
the tutorials tree comes from OMNIDRIVER_OPENCARP_TUTORIALS, and the binary
from the ambient PATH and DYLD_LIBRARY_PATH (evidence A4-A6)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

NIEDERER_RELPATH = "02_EP_tissue/03E_study_resolution"


def opencarp_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_OPENCARP_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_OPENCARP_TUTORIALS is not set. A @pytest.mark.native_opencarp test "
            "needs openCARP's tutorials tree supplied explicitly, e.g.\n"
            "  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials "
            "DYLD_LIBRARY_PATH=/opt/homebrew/lib pytest packages/omnidriver-opencarp/tests -m native_opencarp"
        )
    root = Path(value)
    if not (root / NIEDERER_RELPATH / "nversion.par").is_file():
        pytest.fail(f"OMNIDRIVER_OPENCARP_TUTORIALS={value!r} has no {NIEDERER_RELPATH}/nversion.par")
    return root


def require_opencarp_binary() -> None:
    binary = shutil.which("openCARP")
    if binary is None:
        pytest.fail("openCARP is not on PATH")
    proc = subprocess.run([binary, "-buildinfo"], capture_output=True, text=True)
    if "GIT tag" not in proc.stdout:
        pytest.fail("openCARP cannot start (on macOS, set DYLD_LIBRARY_PATH to the directory "
                    "holding libsundials_cvode; evidence A4-A6): " + proc.stderr[-400:])


import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from omnidriver.core.runtime.models import DataArtifact, data_artifact_from_json
from omnidriver.core.runtime.postprocess_phase import build_sweep_context

from omnidriver.conformance import ConformanceTarget

LAT_PATH = "out/init_acts_vm_act-thresh.dat"


def niederer_sweep(tmp_path: Path, *, dx_values: tuple[float, ...], tend: float,
                   extra: Mapping[str, Any] | None = None,
                   allow_missing_declared_artifact: bool = False) -> Path:
    """Run niedererNVersion over ``dx_values`` through ``omnidriver sweep-run``
    (dt 50 us, G4/G7). Returns the sweep's output directory.

    By default any case that does not complete fails the caller loudly --
    including a missing declared artifact, e.g. the LAT file absent at
    ``all = 0`` (an actual solver or staging defect). Only
    ``test_the_per_event_layout_is_refused_by_name`` (F17) passes
    ``allow_missing_declared_artifact=True``: with ``lats[0].all = 1`` the
    declared per-node LAT file is *expected* to be missing (openCARP writes
    a different file instead, F17), and reconciliation marks that case
    failed even though the solver itself exited 0 -- see
    ``_only_a_declared_artifact_is_missing``. Every other caller must not
    silently tolerate a missing artifact."""
    require_opencarp_binary()
    spec = {
        "base": {"entry": "niedererNVersion", "cases_root": str(opencarp_tutorials_root()),
                 "nversion.par:tend": tend, "nversion.par:dt": 50.0, **(extra or {})},
        "sweep": {"mode": "cross_product", "independent": {"dx": list(dx_values)}},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output = tmp_path / "sweep"
    proc = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", "opencarp", "--spec", str(spec_path),
         "--output-dir", str(output), "--scratch-dir", str(tmp_path / "scratch")],
        capture_output=True, text=True, timeout=600,
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        pytest.fail(f"sweep-run printed no JSON (rc={proc.returncode}): {proc.stderr[-2000:]}")
    for case in payload.get("cases", ()):
        if case.get("status") == "completed":
            continue
        if allow_missing_declared_artifact and _only_a_declared_artifact_is_missing(case):
            continue
        pytest.fail(f"sweep-run failed (rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}")
    if not payload.get("cases"):
        pytest.fail(f"sweep-run produced no cases (rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}")
    return output


def _only_a_declared_artifact_is_missing(case: Mapping[str, Any]) -> bool:
    """Whether ``case`` failed for exactly the reason F17 exercises: the solver
    exited fine, but the LAT artifact (``LAT_PATH``) specifically is absent, so
    reconciliation -- not a crash, a timeout or a refused patch -- marked the
    case failed. Anything else (``materialization_error``, ``plan_error``,
    ``timeout_error``) is a genuine failure and stays fatal, per the
    no-fallbacks rule: this only widens what counts as an *expected* shape,
    it never silences an unexplained one.

    Corrected 2026-09-26 (controller review M11): this used to accept ANY
    missing declared artifact (``missing_count > 0``), so a missing
    ``out/vm.igb`` -- an actual defect -- would have been tolerated right
    alongside F17's expected absence. It now checks which artifact is
    missing, by ``predicted_path``, and refuses to tolerate anything else."""
    if case.get("status") != "failed":
        return False
    if case.get("materialization_error") or case.get("plan_error") or case.get("timeout_error"):
        return False
    reconciliation = case.get("artifact_reconciliation")
    if not reconciliation or reconciliation.get("missing_count", 0) <= 0:
        return False
    missing = [a for a in reconciliation.get("artifacts", ()) if a.get("status") == "missing"]
    return bool(missing) and all(a.get("predicted_path") == LAT_PATH for a in missing)


@dataclass(frozen=True)
class NiedererRun:
    output_dir: Path
    case_id: str
    case_root: Path
    lat_artifact: DataArtifact


def niederer_run(tmp_path: Path, *, dx: float, tend: float, extra: Mapping[str, Any] | None = None,
                 allow_missing_declared_artifact: bool = False) -> NiedererRun:
    output = niederer_sweep(tmp_path, dx_values=(dx,), tend=tend, extra=extra,
                            allow_missing_declared_artifact=allow_missing_declared_artifact)
    (case,) = build_sweep_context(output).cases
    document = json.loads((output / case.run_document_path).read_text())
    artifact = next(data_artifact_from_json(raw) for raw in document["expectedArtifacts"]
                    if raw["path_pattern"] == LAT_PATH)
    return NiedererRun(output, case.case_id, Path(case.case_root), artifact)


def niederer_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """Coarse and short, so the native tier stays seconds long (G4, G7)."""
    require_opencarp_binary()
    return ConformanceTarget(
        plugin="opencarp",
        record="niedererNVersion",
        cases_root=opencarp_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"dx": 1000.0, "nversion.par:tend": 10.0, "nversion.par:dt": 50.0},
        patch=("nversion.par:gregion[0].g_il", 0.2),
        untouched=("nversion.par", ("gregion[0]", "g_it")),
        sweep_name="dx",
        sweep_values=(1000.0, 500.0),
        unknown_name="nversion.par:gregion[0].g_ill",
        solver_command="openCARP",
        environment={},
    )
