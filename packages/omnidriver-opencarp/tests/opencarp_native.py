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
            "OMNIDRIVER_OPENCARP_TUTORIALS is not set. A @pytest.mark.native openCARP test "
            "needs openCARP's tutorials tree supplied explicitly, e.g.\n"
            "  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials "
            "DYLD_LIBRARY_PATH=/opt/homebrew/lib pytest -m native"
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


from omnidriver.conformance import ConformanceTarget


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
