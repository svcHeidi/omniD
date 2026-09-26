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

import os
import shutil
from pathlib import Path

import pytest

from omnidriver.conformance import ConformanceTarget

RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"


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
