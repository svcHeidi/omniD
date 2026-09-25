"""Step 4c's own final proof (docs/superpowers/specs/
2026-09-24-tutorials-are-pointers-design.md): the ``restitutionCurves``
tutorial record, committed and RUN end to end through the real ``omnidriver``
CLI, the real cardiacFoam binary, and the real OpenFOAM v2412 runtime --
not mocked, not a dry preview.

Before step 4c's ``configurationSource`` fix, this failed for every
generic-case/tutorial-record entry: execution (``run_document_exec``)
validated the record's intentionally-empty config against cardiacFoam's
config schema (which requires ``myocardiumSolver``, ``endTime``, and other
concrete fields) and refused the run outright, even though planning/commit
had already produced a perfectly valid case. This test is the regression
gate for that fix actually holding under a real solve, not just a mocked
``build_execution_inputs`` call.

``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered -- this test
FAILS, not skips, when it is unset (the same posture every other
``@pytest.mark.native`` test in this suite takes). It also needs the real
OpenFOAM v2412 runtime and the native cardiacFoam build on this machine;
``omnidriver``'s own environment discovery
(``openfoam.openfoam_environment.discover_openfoam_bashrc``) finds both
ambiently, the same way the interactive pilot run did -- there is no
scratch-supplied substitute for either, per CLAUDE.md's "real case or
native-source drift gate, nothing invented".

Marked ``slow`` (a real solve, ~20-30s measured on this machine, comfortably
under the ~2 minute budget this test was only added because it cleared) in
addition to ``native``.
"""

from __future__ import annotations

import json
import os
import shutil
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

pytestmark = [pytest.mark.native, pytest.mark.slow]

_RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"


def _native_tutorials_root() -> Path:
    """Copied from test_restitution_curves_record_native.py's own helper of
    the same name (not imported: that module is collected standalone and
    this test intentionally has no import-time dependency on it)."""
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


def _stage_scratch_copy(native_root: Path, scratch_root: Path) -> Path:
    """Copy the native case into a scratch tree (never write the native
    tree itself) and coarsen its mesh to the tutorial's own smallest
    documented alternative resolution.

    ``system/blockMeshDict`` documents three uniform resolutions as
    commented-out alternatives (deltaX 0.5/0.2/0.1 mm); the checked-in
    default is the finest (200x30x70 = 420000 cells). This test switches to
    the coarsest, already-documented alternative (40x6x14 = 3360 cells) --
    not an invented geometry, one of the tutorial's own three options --
    solely so a real cardiacFoam solve finishes in seconds rather than
    minutes on this developer machine. Measured interactively (this
    worktree's step 4c pilot run) at 3360 cells: 202000 timesteps
    (endTime=2.02, deltaT=1e-5, the protocol values below) completed in
    well under a second of solver time; the coarser mesh is what keeps the
    real, unmocked CLI round trip (mesh + solve + case commit + workflow
    bookkeeping) comfortably inside this test's slow-marked budget.
    """
    native_case = native_root / _RESTITUTION_CURVES_RELPATH
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")

    scratch_case = scratch_root / "tutorials" / _RESTITUTION_CURVES_RELPATH
    shutil.copytree(native_case, scratch_case)

    block_mesh_dict = scratch_case / "system" / "blockMeshDict"
    text = block_mesh_dict.read_text()
    coarse_line = "    // hex (0 1 2 3 4 5 6 7) (40 6 14) simpleGrading (1 1 1)"
    fine_line = "    hex (0 1 2 3 4 5 6 7) (200 30 70) simpleGrading (1 1 1)"
    assert coarse_line in text, "the tutorial's own coarse alternative moved or was reworded"
    assert fine_line in text, "the tutorial's own fine default moved or was reworded"
    text = text.replace(coarse_line, "    hex (0 1 2 3 4 5 6 7) (40 6 14) simpleGrading (1 1 1)")
    text = text.replace(fine_line, "    // hex (0 1 2 3 4 5 6 7) (200 30 70) simpleGrading (1 1 1)")
    block_mesh_dict.write_text(text)

    return scratch_root / "tutorials"


def test_restitution_curves_single_case_reaches_completed_via_the_real_cli(
    tmp_path: Path,
) -> None:
    native_root = _native_tutorials_root()
    cases_root = _stage_scratch_copy(native_root, tmp_path / "native-scratch")

    # A scratch VARIANT of the real study (design's own instruction: narrow
    # to one case, never edit the native file) -- the first S2 value the
    # real tworldS1S2Restitution/sweep.json sweeps, unchanged, so this is a
    # real protocol point, not an invented one.
    spec = {
        "base": {
            "entry": "restitutionCurves",
            "cases_root": str(cases_root),
            "ionicModel": "TWorld",
            "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
        },
        "sweep": {
            "mode": "zip",
            "independent": {
                "s1s2Protocol": [
                    {"s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 1500},
                ],
            },
        },
    }
    spec_path = tmp_path / "scratch_sweep.json"
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"

    from omnidriver.cli import main

    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "sweep-run", "--spec", str(spec_path), "--output-dir", str(output_dir),
        ])

    result = json.loads(out.getvalue())
    assert code == 0, result
    assert result["completed_count"] == 1, result
    assert result["failed_count"] == 0, result
    [case] = result["cases"]
    assert case["status"] == "completed", case

    workflow_state = json.loads(
        (output_dir / "cases" / "case_0001" / "workflow_state.json").read_text()
    )
    assert workflow_state["status"] == "completed"
    assert workflow_state["completed_steps"] == ["mesh", "solve"]
    assert workflow_state["failed_step_id"] is None
    for step in workflow_state["steps"]:
        assert step["status"] == "completed", step
        assert step["exit_code"] == 0, step

    # Step 4c's own regression: the committed record case is "case"-sourced
    # and its (structurally empty) config was never checked against the
    # plugin's schema -- this is what let execution proceed at all.
    run_document = json.loads(
        (output_dir / "case_0001" / "run_document.json").read_text()
    )
    assert run_document["configurationSource"] == "case"

    # A real cardiacFoam solve happened: its own post-processing trace file
    # exists and has real solver output in it (a header plus many samples,
    # not an empty stub).
    solved_case = output_dir / "cases" / "case_0001"
    trace_files = list((solved_case / "postProcessing").glob("*.txt"))
    assert trace_files, "cardiacFoam wrote no postProcessing trace file"
    trace_lines = trace_files[0].read_text().splitlines()
    assert len(trace_lines) > 1000, (
        f"expected a real multi-timestep trace, got {len(trace_lines)} lines"
    )
