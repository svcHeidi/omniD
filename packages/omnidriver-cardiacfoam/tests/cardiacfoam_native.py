"""Supplied inputs for native cardiacFOAM tests, and one conformance target
per tutorial record (tutorials-are-pointers plan §5f; conformance Task 14).

A uniquely named module, not ``conftest``: CLAUDE.md's conftest trap (core's
conftest wins a ``from conftest import X`` when the whole repo is collected).

Nothing here is discovered. The native tutorials tree comes from
``OMNIDRIVER_NATIVE_TUTORIALS``, and the OpenFOAM environment from the shell
the tests run in, already sourced (plan §2 item 6): every child process a
conformance check starts inherits it (``conformance.checks._child_env``).
Point ``OMNIDRIVER_NATIVE_TUTORIALS`` at a clean native worktree's
``tutorials/`` (plan §4), never at a checkout holding run output in place.

Every tutorial record adds its own ``*_conformance_target(tmp_path)`` here
and joins ``test_conformance_native.py``'s parametrization.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from omnidriver.conformance import ConformanceTarget
from omnidriver.core.runtime.models import DataArtifact, data_artifact_from_json
from omnidriver.core.runtime.postprocess_phase import build_sweep_context

RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
NIEDERER_2011_RELPATH = "NiedererEtAl2011verification"
#: The literal path topic B Task 7's reader turns into a
#: ``ProducedPath(path, "cardiacfoam_activation_probes")`` (plan §5c, item 2):
#: written last by the ``samplePoints`` step
#: (``postProcess -func Niedererpoints -latestTime``), confirmed by a real
#: run (``docs/solver-learning/cardiacfoam.md``, section N).
NIEDERER_POINTS_PATH = "postProcessing/Niedererpoints/0/activationTime"


def native_tutorials_root() -> Path:
    """The supplied native tutorials tree. FAILS, never skips, when unset:
    a ``native`` test that cannot see the real tree proves nothing."""
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
    """The calling shell has OpenFOAM sourced and ``commands`` on its PATH.
    Checked up front so a missing environment fails naming the fix, rather
    than as C5-C11 verdicts about a plan that could not run."""
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
    """``manufacturedEikonalECG`` at the coarsest resolution any of its
    studies define (``numberCells: 10``, ``cartesianConvergence``'s own
    coarsest point) -- a real hex/blockMesh run takes well under a minute
    (docs/solver-learning/cardiacfoam.md, section E: 10x10x10 completed in
    13 s)."""
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


def restitution_curves_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``restitutionCurves`` at the coarsest mesh ``system/blockMeshDict``
    documents (40x6x14, deltaX 0.5 mm), the one step 4c ran. Everything
    else is the native case's own: BuenoOrovio, epicardialCells, S1 2000 ms
    x10 then S2 250 ms x2, endTime 20.5 -- a real run takes seconds."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="restitutionCurves",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"blockMeshResolution": [40, 6, 14]},
        # A catalogued enum key (``$ELECTRO_MODEL_COEFFS.tissue``), and its
        # sibling in the same ``singleCellSolverCoeffs`` scope.
        patch=("constant/electroProperties:singleCellSolverCoeffs.tissue", "endocardialCells"),
        untouched=("constant/electroProperties", ("singleCellSolverCoeffs", "ionicModel")),
        # The two coarsest of the three resolutions the native
        # blockMeshDict documents (deltaX 0.5 mm and 0.2 mm).
        sweep_name="blockMeshResolution",
        sweep_values=([40, 6, 14], [100, 15, 35]),
        unknown_name="constant/electroProperties:singleCellSolverCoeffs.tissu",
        solver_command="cardiacFoam",
        environment={},
    )


def manufactured_bidomain_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``manufacturedBidomain`` at its coarsest hex resolution (a 5x5x5 box,
    a real run in well under a second -- module docstring evidence: N=5
    produced ``postProcessing/3D_5_cells.dat`` and ran to completion in the
    real solver log's own ``ExecutionTime = 0.04 s``)."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    return ConformanceTarget(
        plugin="cardiacfoam",
        record="manufacturedBidomain",
        cases_root=native_tutorials_root(),
        scratch_root=tmp_path / "scratch",
        base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10},
        # A cataloged enum key (`$ELECTRO_MODEL_COEFFS.verificationModel.k`,
        # applicable to `manufacturedFDABidomainVerifier` since this
        # module's own 2026-09-26 catalog correction), read at the native
        # default 1.0/sqrt(2) when absent (manufacturedFDABidomainVerifier.C).
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


def niederer_sweep(tmp_path: Path, *, dx: float, end_time: float | None = None,
                    extra: Mapping[str, Any] | None = None) -> Path:
    """Run ``niederer2011`` (hex route) at one ``dx`` (metres) through
    ``omnidriver sweep-run``, against the supplied native tree. Returns the
    sweep's output directory. Any case that does not complete fails the
    caller loudly (mirrors ``omnidriver-opencarp``'s ``opencarp_native
    .niederer_sweep``)."""
    require_sourced_openfoam("blockMesh", "cardiacFoam")
    base: dict[str, Any] = {
        "entry": "niederer2011", "cases_root": str(native_tutorials_root()),
        **(extra or {}),
    }
    if end_time is not None:
        base["system/controlDict:endTime"] = end_time
    spec = {
        "base": base,
        "sweep": {"mode": "cross_product", "independent": {"dx": [dx]}},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output = tmp_path / "sweep"
    proc = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", "cardiacfoam",
         "--spec", str(spec_path), "--output-dir", str(output),
         "--scratch-dir", str(tmp_path / "scratch")],
        capture_output=True, text=True, timeout=600,
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
    """``niederer2011`` at one ``dx``, run for real -- the counterpart of
    ``omnidriver-opencarp``'s ``opencarp_native.niederer_run``, for topic B
    Task 7's own tests. Returns ``(case_root, probe)``, where ``probe`` is
    the declared ``samplePoints`` artifact for :data:`NIEDERER_POINTS_PATH`."""
    output = niederer_sweep(tmp_path, dx=dx, end_time=end_time)
    (case,) = build_sweep_context(output).cases
    document = json.loads((output / case.run_document_path).read_text())
    artifact = next(
        data_artifact_from_json(raw) for raw in document["expectedArtifacts"]
        if raw["path_pattern"] == NIEDERER_POINTS_PATH
    )
    return Path(case.case_root), artifact


def niederer2011_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``niederer2011`` (hex route) at the coarsest resolution its own
    ``cartesianConvergence`` study defines (dx 0.5 mm -> cells (40 6 14)),
    the native ``endTime`` (0.015 s) left unchanged so the real run stays a
    few seconds long."""
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
