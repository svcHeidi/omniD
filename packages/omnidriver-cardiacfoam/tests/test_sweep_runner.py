#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_sweep_runner
#
# Description
#     Tests sweep_plan/sweep_run orchestration against real cardiac routing
#     and materialization.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Sweep-runner tests that exercise real cardiac routing/materialization.

Moved out of core's test tree (Part B, test-ownership split): these eight
tests run ``route_case_values``/``materialize_case``/``strict_plan`` for
real (no mocking of the routing or materialization step) and assert on
cardiac-specific output -- ``constant/electroProperties`` written to disk,
TNNP accepted vs an unrecognized ionic model rejected, real solver
invocation via subprocess. None of that is meaningful under a generic/
neutral plugin, so unlike the tests that stayed in
``packages/omnidriver/tests/core/test_sweep_runner.py`` (entry-mode tests
that mock ``load_entry_spec``; resume/fresh/retry/timeout tests that mock
``route_case_values`` directly with content-free axis vocabulary; the
over-cap and hash-mismatch tests, which never reach routing at all), these
cannot be made to pass under core alone without mocking away the exact
behavior they exist to prove.

This file used to be hidden from core's collection entirely behind a
module-level ``pytest.importorskip("omnidriver.cardiacfoam...")`` (see
``tests/core/test_no_new_core_tests_are_hidden.py``'s now-shrunk
``KNOWN_HIDDEN_FILES``); it runs unconditionally here since
omnidriver-cardiacfoam is this package's own subject.
"""

from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path
from unittest import mock

import pytest

from omnidriver.core.runtime.sweep_runner import sweep_plan, sweep_run
from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(
    CardiacFoamPlugin(), source="test:sweep_runner",
)

#: These two tests invoke a REAL solver run: sweep_run shells out to
#: `python -m omnidriver run`, whose workflow executes `Allrun`, which invokes
#: the `cardiacFoam` binary. Without an OpenFOAM environment they report every
#: case failed, with no materialization_error and no plan_error -- the failure
#: is in the subprocess, so nothing surfaces in the sweep result.
#:
#: They were silently environment-dependent: green on a machine where OpenFOAM
#: happened to be reachable, red otherwise, with nothing in the test saying so.
#: `run_case.sh` hardcodes `/Volumes/OpenFOAM-v2412/etc/bashrc` as its fallback,
#: which does not match this machine's `/Volumes/OpenFOAM/OpenFOAM-12`, so even
#: a mounted install may not resolve.
#:
#: The `integration` marker was declared in the root pyproject.toml for exactly
#: this ("tests requiring a real cardiacFoam binary, skipped by default in CI")
#: and had never been applied to anything. A marker alone does not skip, so the
#: skipif is what actually makes the dependency honest; the marker lets CI
#: deselect the whole class with -m "not integration".
_HAS_SOLVER = shutil.which("cardiacFoam") is not None
requires_solver = pytest.mark.skipif(
    not _HAS_SOLVER,
    reason="needs a real cardiacFoam binary on PATH (sweep_run executes Allrun)",
)



def _write_spec(path: Path, models=("TNNP", "BuenoOrovio")):
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"ionicModel": list(models)},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["ionicModel"]}],
        },
    }
    path.write_text(json.dumps(spec))
    return spec


@pytest.mark.integration
@requires_solver
def test_sweep_run_writes_case_record_json_for_every_case(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_spec(spec_path)
    output_dir = tmp_path / "out"

    result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert result["completed_count"] == 2
    for case_id in ("TNNP", "BuenoOrovio"):
        record_path = output_dir / case_id / "case_record.json"
        assert record_path.is_file()
        record = json.loads(record_path.read_text())
        assert record["case_id"] == case_id
        assert record["status"] == "completed"


def test_sweep_run_writes_case_record_json_even_when_a_case_fails(tmp_path):
    # case_record.json must exist for every case regardless of whether the
    # whole sweep succeeded -- an agent diagnosing a partially-failed sweep
    # needs the successful cases' records just as much as a clean sweep does.
    spec_path = tmp_path / "sweep.json"
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"ionicModel": ["TNNP", "not_a_real_model"]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["ionicModel"]}],
        },
    }
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"

    result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert result["failed_count"] >= 1
    assert (output_dir / "TNNP" / "case_record.json").is_file()


@pytest.mark.integration
@requires_solver
def test_sweep_run_archives_nothing_for_generic_case_folder_sweeps(tmp_path):
    # archive_dir_name only applies to entry mode (see sweep_runner.sweep_run's
    # archive_dir_name assignment) -- a generic/case-folder sweep must not
    # gain a spurious "collectedOutput" subfolder just because the default
    # changed from None to a string.
    spec_path = tmp_path / "sweep.json"
    _write_spec(spec_path)
    output_dir = tmp_path / "out"

    result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert result["completed_count"] == 2
    for case_id in ("TNNP", "BuenoOrovio"):
        assert not (output_dir / case_id / "collectedOutput").exists()


def test_sweep_plan_materializes_and_audits_each_case_for_real(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_spec(spec_path)
    output_dir = tmp_path / "out"

    result = sweep_plan(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert result["case_count"] == 2
    assert {c["case_id"] for c in result["cases"]} == {"TNNP", "BuenoOrovio"}
    for case in result["cases"]:
        assert case["plan"]["status"] == "ok"
        assert (output_dir / case["case_id"] / "constant" / "electroProperties").exists()


def test_sweep_plan_records_materialization_failure_and_continues(tmp_path):
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"ionicModel": ["TNNP", "NotARealModel"]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["ionicModel"]}],
        },
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    by_id = {case["case_id"]: case for case in result["cases"]}
    assert by_id["TNNP"]["status"] == "ok"
    assert by_id["NotARealModel"]["status"] == "failed"
    assert "materialization_error" in by_id["NotARealModel"]


def test_sweep_plan_records_unrecognized_axis_as_per_case_failure(tmp_path):
    # route_case_values now raises SweepValidationError for an unrecognized
    # axis like "bogusAxis" (see sweep_routing.py fix). That per-case error
    # must be caught and recorded like any other materialization failure,
    # not propagate uncaught and crash the whole sweep_plan call -- a caller
    # sweeping N cases with one bad axis should still see a clean per-case
    # report, the same as an invalid ionicModel does today.
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "myocyte"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"bogusAxis": [0.5, 0.2]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["bogusAxis"]}],
        },
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "failed"
        assert "bogusAxis" in case["materialization_error"]


def test_sweep_run_writes_run_documents_and_continues_past_failure(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_spec(spec_path)
    output_dir = tmp_path / "out"

    call_log = []
    real_subprocess_run = subprocess.run  # captured before patching, so real internal
    # subprocess calls materialize_case makes (e.g. foamDictionary, when it's on PATH)
    # still execute for real instead of being swallowed by this fake.

    def fake_subprocess_run(cmd, **kwargs):
        if "--run-document" not in cmd:
            return real_subprocess_run(cmd, **kwargs)
        call_log.append(cmd)
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        failed = "BuenoOrovio" in str(run_doc_path.parent)
        state = {"status": "failed" if failed else "completed"}
        workflow_state_path.write_text(json.dumps(state))
        return mock.Mock(returncode=1 if failed else 0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run):
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert len(call_log) == 2
    assert (output_dir / "TNNP" / "run_document.json").exists()
    assert (output_dir / "BuenoOrovio" / "run_document.json").exists()
    run_doc = json.loads((output_dir / "TNNP" / "run_document.json").read_text())
    step = run_doc["workflowDag"]["steps"][0]
    assert step["id"] == "run"
    assert step["command"] == "Allrun"
    assert step["depends_on"] == []
    state_step = run_doc["workflowState"]["steps"][0]
    assert state_step["step_id"] == "run"
    assert state_step["status"] == "pending"
    assert state_step["attempt"] == 0

    manifest_path = output_dir / "sweep_manifest.json"
    assert manifest_path.exists()
    from omnidriver.core.runtime.sweep_manifest import read_manifest
    manifest = read_manifest(manifest_path)
    statuses = {c.case_id: c.status for c in manifest.cases}
    assert statuses["TNNP"] == "completed"
    assert statuses["BuenoOrovio"] == "failed"
    state_paths = {c.case_id: c.workflow_state_path for c in manifest.cases}
    assert state_paths["TNNP"] == "TNNP/postProcessing/workflow_state.json"
    assert result["failed_count"] == 1
    assert result["completed_count"] == 1
    assert result["postprocess"]["status"] == "skipped"


def test_sweep_run_records_unrecognized_axis_as_per_case_failure(tmp_path):
    # Mirrors test_sweep_plan_records_unrecognized_axis_as_per_case_failure:
    # route_case_values's SweepValidationError must be caught per-case inside
    # sweep_run's loop too, not crash the whole call.
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "myocyte"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"bogusAxis": [0.5, 0.2]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["bogusAxis"]}],
        },
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))

    from omnidriver.core.runtime.sweep_runner import sweep_run
    with mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run") as mock_run:
        result = sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    mock_run.assert_not_called()
    assert result["failed_count"] == 2
    assert result["completed_count"] == 0
    for case in result["cases"]:
        assert case["status"] == "failed"
        assert "bogusAxis" in case["materialization_error"]
