"""P1's own real proof (docs/superpowers/specs/2026-09-24-tutorials-are-
pointers-design.md, step 5.0): `plan --strict --entry <record>` -- and the
`run --run-document <path>` command it advertises -- work end to end
against the real ``restitutionCurves`` tutorial record, the real
cardiacFoam binary, and the real OpenFOAM v2412 runtime.

Before this fix, `omnidriver --plugin cardiacfoam plan --strict --entry
restitutionCurves ...` raised a raw ``TutorialRecordError`` traceback
(`registry._materialize_resolved_entry`'s own refusal: "tutorial records
are not yet runnable through load_entry_spec") -- the ONLY working path was
`sweep-run` (`test_restitution_curves_real_solver_run_native.py`, step 4c).
This test is the direct `plan --strict`/`run --run-document` counterpart of
that same real run, over the SAME single protocol point, coarsened the SAME
way (the `blockMeshResolution` axis, never a case-file edit).

``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered -- this test
FAILS, not skips, when it is unset, the same posture every other
``@pytest.mark.native`` test in this suite takes. It also needs the real
OpenFOAM v2412 runtime and the native cardiacFoam build on this machine,
found ambiently exactly as step 4c's test finds them.

Marked ``slow`` (a real solve, ~20-30s measured for the same case/mesh in
step 4c) in addition to ``native``.
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
    """Copied from test_restitution_curves_real_solver_run_native.py's own
    helper of the same name (not imported: that module is collected
    standalone and this test intentionally has no import-time dependency on
    it)."""
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
    tree itself). The coarse mesh is a study value, resolved through the
    record's own `blockMeshResolution` axis and committed through the
    normal render/commit channel by `plan --strict` itself -- not a text
    edit here."""
    native_case = native_root / _RESTITUTION_CURVES_RELPATH
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")

    scratch_case = scratch_root / "tutorials" / _RESTITUTION_CURVES_RELPATH
    shutil.copytree(native_case, scratch_case)

    return scratch_root / "tutorials"


def test_restitution_curves_plan_strict_and_its_advertised_run_document_reach_completed(
    tmp_path: Path,
) -> None:
    native_root = _native_tutorials_root()
    cases_root = _stage_scratch_copy(native_root, tmp_path / "native-scratch")

    # The same single, real protocol point step 4c's sweep-based test uses
    # (the real tworldS1S2Restitution/sweep.json's own first point,
    # unchanged) -- supplied here as a `--config` section, since a single
    # `plan --strict --entry <record>` has no sweep expansion of its own:
    # every value below becomes this one case's study `base` directly.
    config = {
        "restitutionCurves": {
            "ionicModel": "TWorld",
            "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            "blockMeshResolution": [40, 6, 14],
            "s1s2Protocol": {
                "s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 1500,
            },
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))

    from omnidriver.cli import main

    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "plan", "--strict", "--entry", "restitutionCurves",
            "--config", str(config_path),
            "--cases-root", str(cases_root),
            "--scratch-dir", str(tmp_path / "scratch"),
        ])
    plan_payload = json.loads(out.getvalue())
    assert code == 0, plan_payload
    assert plan_payload["status"] == "ok", plan_payload

    command = plan_payload["launch"]["command"]
    assert "--run-document" in command, command
    assert "--strict" not in command
    assert "--entry" not in command
    run_document_path = Path(command[command.index("--run-document") + 1])
    assert run_document_path.is_file(), (
        "plan --strict must persist the run document it advertises, so the "
        "command it prints is immediately runnable"
    )
    committed_document = json.loads(run_document_path.read_text())
    assert committed_document["configurationSource"] == "case"
    case_root = Path(committed_document["launch"]["caseRoot"])

    # The advertised command itself:
    # [sys.executable, "-m", "omnidriver", "run", "--plugin", "cardiacfoam",
    #  "--run-document", <path>] -- run it in-process by dropping the
    # interpreter/module-invocation prefix, the same way
    # test_cli_plan_strict_tutorial_record.py's core-plugin equivalent does.
    assert command[:3] == [command[0], "-m", "omnidriver"]
    out = StringIO()
    with redirect_stdout(out):
        code = main(command[3:])
    run_payload = json.loads(out.getvalue())
    assert code == 0, run_payload
    assert run_payload["status"] == "ok", run_payload
    workflow_state = run_payload["workflow_state"]
    assert workflow_state["status"] == "completed", workflow_state
    assert workflow_state["completed_steps"] == ["mesh", "solve"]
    assert workflow_state["failed_step_id"] is None
    for step in run_payload["steps"]:
        assert step["exit_code"] == 0, step

    # A real cardiacFoam solve happened.
    trace_files = list((case_root / "postProcessing").glob("*.txt"))
    assert trace_files, "cardiacFoam wrote no postProcessing trace file"
    trace_lines = trace_files[0].read_text().splitlines()
    assert len(trace_lines) > 1000, (
        f"expected a real multi-timestep trace, got {len(trace_lines)} lines"
    )

    # The `blockMeshResolution` axis's own patch reached the committed case
    # through the normal render/commit channel `plan --strict` itself ran --
    # never a text-swap this test performed.
    block_mesh_dict = (case_root / "system" / "blockMeshDict").read_text()
    active_hex_lines = [
        line.strip() for line in block_mesh_dict.splitlines()
        if line.strip().startswith("hex (")
    ]
    assert len(active_hex_lines) == 1, (
        f"expected exactly one active hex block, got {active_hex_lines}"
    )
    assert "(40 6 14)" in active_hex_lines[0], active_hex_lines[0]
