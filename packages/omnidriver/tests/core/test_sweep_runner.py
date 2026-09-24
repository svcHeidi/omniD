import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from omnidriver.core.runtime.sweep_runner import (
    _completed_case_is_reusable,
    _run_case_process,
    _stage_entry_case,
    sweep_plan,
    sweep_run,
)
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.attempt_lease import AttemptLeaseError, acquire_case_lease
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, compute_override_hash
from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions

# Phase 2 Task 5b / test-ownership split: this file used to require
# omnidriver-cardiacfoam (its specs were cardiac vocabulary throughout --
# a real tutorial entry name, ionic models, electro/physics selectors) and
# was hidden from core's collection behind an importorskip. The remaining
# fixture names below are now neutral placeholders (review's own vocabulary
# cleanup, 2026-09-24) -- they never named real cardiac routing to begin
# with. The 11 tests that genuinely
# exercise real cardiac routing/materialization moved to
# packages/omnidriver-cardiacfoam/tests/test_sweep_runner.py, where they run
# against the real plugin. What remains here either never reaches routing at
# all (entry-mode tests mock load_entry_spec; the over-cap/hash-mismatch
# tests raise before any per-case work), or mocks
# omnidriver.core.runtime.sweep_runner.route_case_values directly and uses
# content-free axis vocabulary -- so it needs only *a* plugin, not the
# cardiac one, to prove core's own sweep bookkeeping (resume/fresh/retry/
# timeout/archive) still works.
from omnidriver.core.plugin_interface import driver_context as _driver_context
from plugins.declared_case_plugin import DeclaredCasePlugin
from plugins.resume_test_plugin import ResumeTestPlugin

_CTX = _driver_context(ResumeTestPlugin(), source="test:sweep_runner")


class _StagingConventionPlugin(DeclaredCasePlugin):
    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(
            output_collection_relpath="postProcessing",
            generated_directory_names=("postProcessing", "workflow_logs"),
            generated_file_names=("workflow_state.json",),
            generated_case_markers=("workflow_state.json", "workflow_logs"),
            decomposition_directory_prefix="processor",
            time_directory_name_pattern=r"^-?\d+(\.\d+)?(e[+\-]?\d+)?$",
            preserved_time_directory_names=("0",),
        )


class _PostProcessingOutputPlugin(DeclaredCasePlugin):
    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(output_collection_relpath="postProcessing")


_STAGING_CTX = _driver_context(_StagingConventionPlugin(), source="test:staging")
_POSTPROCESSING_CTX = _driver_context(_PostProcessingOutputPlugin(), source="test:postprocessing")


def _write_spec(path: Path, models=("TNNP", "BuenoOrovio")):
    spec = {
        "base": {
            "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
            "physics_selectors": {"type": "electroModel"},
        },
        "sweep": {
            "mode": "cross_product",
            "independent": {"modelName": list(models)},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["modelName"]}],
        },
    }
    path.write_text(json.dumps(spec))
    return spec


def _write_entry_spec(path, entry="sampleTutorial", values=(0.5, 0.2)):
    spec = {
        "base": {"entry": entry},
        "sweep": {
            "mode": "cross_product",
            "independent": {"dx_values": [[v] for v in values]},
            "dependent": [{"name": "caseId", "derive": "output_dir_name_template", "of": ["dx_values"]}],
        },
    }
    path.write_text(json.dumps(spec))
    return spec


def _write_placeholder_spec(path: Path, values=("x",)):
    """A cross_product spec with no plugin-specific axis vocabulary.

    Used by the resume/fresh/retry/timeout tests below, which mock
    ``route_case_values`` directly and assert only on sweep-runner
    bookkeeping (skip/retry/outcome/manifest), never on what routing
    itself produced -- so the axis name and values are placeholders, not
    a stand-in for any real solver parameter."""
    spec = {
        "base": {},
        "sweep": {
            "mode": "cross_product",
            "independent": {"param": list(values)},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["param"]}],
        },
    }
    path.write_text(json.dumps(spec))
    return spec


def test_completed_sweep_reuse_checks_input_identity_and_required_outputs(tmp_path, monkeypatch):
    """The manifest's completed bit alone can never skip a changed case."""
    case_root = tmp_path / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "constant").mkdir()
    settings = case_root / "system" / "settings"
    settings.write_text("value 1;\n")
    dag = {"steps": [{
        "id": "solve", "command": sys.executable,
        "args": ["-c", "from pathlib import Path; Path('result.txt').write_text('done')"],
        "cwd": ".", "depends_on": [], "produces": [], "consumes": [],
        "retry_policy": {"max_attempts": 1},
    }]}
    state = initial_workflow_state(dag)
    assert state is not None
    output_dir = tmp_path / "out"
    state_path = output_dir / "x" / "workflow_state.json"
    result = run_workflow_step(
        dag, state, "solve", case_root=case_root, log_dir=output_dir / "logs",
        state_path=state_path, env={}, driver_context=_CTX,
    )
    assert result.state.status == "completed"
    prior_entry = CaseManifestEntry(
        case_id="x", resolved_axis_values={}, override_hash=compute_override_hash({}),
        run_document_path="x/run_document.json", workflow_state_path="x/workflow_state.json",
        status="completed", outcome="fresh", started_at="t0", updated_at="t0",
    )
    document = SimpleNamespace(
        workflowDag=dag,
        launch={"caseRoot": str(case_root)},
        expectedArtifacts=[{"artifact_id": "result", "path_pattern": "result.txt", "format": "text"}],
    )
    monkeypatch.setattr("omnidriver.core.runtime.sweep_runner.load_run_document", lambda _: document)
    assert _completed_case_is_reusable(
        prior_entry, output_dir=output_dir, routed={}, driver_context=_CTX,
        execution_environment={},
    ) == (True, None)
    settings.write_text("value 2;\n")
    reusable, error = _completed_case_is_reusable(
        prior_entry, output_dir=output_dir, routed={}, driver_context=_CTX,
        execution_environment={},
    )
    assert not reusable and "input evidence changed" in error
    settings.write_text("value 1;\n")
    (case_root / "result.txt").unlink()
    reusable, error = _completed_case_is_reusable(
        prior_entry, output_dir=output_dir, routed={}, driver_context=_CTX,
        execution_environment={},
    )
    assert not reusable and "required outputs are missing" in error


def test_entry_case_staging_keeps_authored_case_clean(tmp_path):
    source = tmp_path / "tutorials" / "case"
    source.mkdir(parents=True)
    (source / "system").mkdir()
    (source / "system" / "controlDict").write_text("endTime 0.2;\n")
    (source / "0").mkdir()
    (source / "0" / "Vm").write_text("initial field")
    (source / "postProcessing").mkdir()
    (source / "postProcessing" / "old.dat").write_text("stale")
    (source / "processor0").mkdir()
    (source / "processor0" / "old").write_text("stale")
    (source / "0.2").mkdir()
    (source / "0.2" / "Vm").write_text("stale")
    (source / "workflow_state.json").write_text("{}")
    generated_case = source / "gauss_linear_40_manufacturedVerifier"
    (generated_case / "workflow_logs").mkdir(parents=True)
    (generated_case / "system").mkdir()
    (generated_case / "system" / "controlDict").write_text("generated")

    staged = tmp_path / "scratch" / "case_0001"
    _stage_entry_case(source, staged, driver_context=_STAGING_CTX)

    assert (staged / "system" / "controlDict").read_text() == "endTime 0.2;\n"
    assert (staged / "0" / "Vm").exists()
    assert not (staged / "postProcessing").exists()
    assert not (staged / "processor0").exists()
    assert not (staged / "0.2").exists()
    assert not (staged / "workflow_state.json").exists()
    assert not (staged / generated_case.name).exists()
    assert (source / "postProcessing" / "old.dat").exists()


def test_neutral_staging_preserves_authored_paths_named_like_openfoam_outputs(tmp_path):
    """Only an environment declaration may classify these names as generated."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "data").mkdir()
    (source / "data" / "protocol.json").write_text("authored")
    (source / "postProcessing").mkdir()
    (source / "postProcessing" / "notes.txt").write_text("also authored")
    staged = tmp_path / "staged"

    _stage_entry_case(source, staged, driver_context=_CTX)

    assert (staged / "data" / "protocol.json").read_text() == "authored"
    assert (staged / "postProcessing" / "notes.txt").read_text() == "also authored"


def test_entry_case_staging_refuses_to_replace_a_live_case(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "system").mkdir()
    (source / "system" / "controlDict").write_text("new\n")
    staged = tmp_path / "scratch" / "case"
    staged.mkdir(parents=True)
    (staged / "live-result").write_text("must survive")

    with acquire_case_lease(staged):
        with pytest.raises(AttemptLeaseError, match="already owned"):
            _stage_entry_case(source, staged)

    assert (staged / "live-result").read_text() == "must survive"
    _stage_entry_case(source, staged)
    assert not (staged / "live-result").exists()
    assert (staged / "system" / "controlDict").read_text() == "new\n"


def test_entry_case_staging_copy_failure_leaves_existing_case_untouched(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    staged = tmp_path / "scratch" / "case"
    staged.mkdir(parents=True)
    (staged / "live-result").write_text("must survive")

    def fail_copy(*_args, **_kwargs):
        raise OSError("simulated copy failure")

    monkeypatch.setattr("omnidriver.core.runtime.sweep_runner.shutil.copytree", fail_copy)
    with pytest.raises(OSError, match="simulated copy failure"):
        _stage_entry_case(source, staged)

    assert (staged / "live-result").read_text() == "must survive"


def test_entry_case_staging_recovers_prior_case_after_interrupted_promotion(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "system").mkdir()
    (source / "system" / "controlDict").write_text("new\n")
    staged = tmp_path / "scratch" / "case"
    staged.mkdir(parents=True)
    (staged / "system").mkdir()
    (staged / "system" / "controlDict").write_text("old\n")

    real_replace = os.replace
    failed = False

    def interrupt_candidate_promotion(source_path, destination_path):
        nonlocal failed
        source_name = Path(source_path).name
        if (
            not failed
            and ".omnidriver-candidate-" in source_name
            and Path(destination_path) == staged
        ):
            failed = True
            raise OSError("simulated interruption during promotion")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr("omnidriver.core.runtime.sweep_runner.os.replace", interrupt_candidate_promotion)
    with pytest.raises(OSError, match="simulated interruption"):
        _stage_entry_case(source, staged)

    # The target is absent only while the durable journal and old sibling are
    # present. A later holder restores the prior tree before restaging.
    assert not staged.exists()
    _stage_entry_case(source, staged)
    assert (staged / "system" / "controlDict").read_text() == "new\n"
    leftovers = [
        path for path in staged.parent.glob(".case.omnidriver-*")
        if "candidate" in path.name or "backup" in path.name or "staging" in path.name
    ]
    assert not leftovers


def test_sweep_plan_entry_mode_materializes_via_apply_case_and_audits(tmp_path):
    # Entry-based sweeps target an existing registered tutorial whose
    # apply_case()/build_cases() mutate its own shared case_root in place
    # (confirmed empirically for sampleTutorial -- it is not a from-scratch
    # case_folder). sweep_plan must call spec.build_cases() + spec.apply_case()
    # directly instead of materialize_case()/build_and_launch, then audit via
    # strict_plan with the same routed overrides.
    spec_path = tmp_path / "sweep.json"
    _write_entry_spec(spec_path)

    fake_case_config = mock.Mock(case_id="implicit_TNNP_DX0.5")
    fake_spec = mock.Mock()
    fake_spec.plan_case = None
    fake_spec.case_root = tmp_path / "case_root"
    fake_spec.build_cases.return_value = [fake_case_config]

    fake_report = mock.Mock()
    fake_report.status = "ok"
    fake_report.to_json.return_value = {
        "status": "ok",
        "run_document": {"version": "3", "launch": {"outputDir": str(tmp_path / "out")}},
    }

    with mock.patch("omnidriver.core.runtime.sweep_runner.load_entry_spec", return_value=fake_spec) as mock_load, \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report) as mock_strict_plan, \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize:
        result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    mock_materialize.assert_not_called()
    assert mock_load.call_count == 2
    for call in mock_load.call_args_list:
        args, kwargs = call
        assert args[0] == "sampleTutorial"
        assert "dx_values" in kwargs["overrides"]
        assert "caseId" not in kwargs["overrides"]
    fake_spec.apply_case.assert_has_calls(
        [mock.call(fake_spec.case_root, fake_case_config)] * 2
    )
    assert mock_strict_plan.call_count == 2
    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "ok"


def test_sweep_plan_entry_mode_rejects_axis_combination_resolving_to_multiple_cases(tmp_path):
    # sweep-run's per-axis-combination model assumes exactly one case per
    # resolved combination (see route_entry_case_values docstring); a
    # combination that still fans out inside the tutorial's own build_cases()
    # (e.g. missing a constraining kwarg like "solvers") must fail loudly as
    # a per-case error, not silently apply_case() only the first of several.
    spec_path = tmp_path / "sweep.json"
    _write_entry_spec(spec_path, values=(0.5,))

    fake_spec = mock.Mock()
    fake_spec.plan_case = None
    fake_spec.case_root = tmp_path / "case_root"
    fake_spec.build_cases.return_value = [mock.Mock(), mock.Mock()]

    with mock.patch("omnidriver.core.runtime.sweep_runner.load_entry_spec", return_value=fake_spec):
        result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    fake_spec.apply_case.assert_not_called()
    assert result["cases"][0]["status"] == "failed"
    assert "2 cases" in result["cases"][0]["materialization_error"]


def test_sweep_run_entry_mode_executes_run_document_sequentially(tmp_path):
    # Because apply_case mutates the tutorial's shared case_root in place,
    # entry-mode sweep-run must process cases strictly one at a time (never
    # in parallel) -- already guaranteed by sweep_run's plain synchronous
    # for-loop, verified here by asserting apply_case/subprocess.run calls
    # happen in resolved-case order.
    spec_path = tmp_path / "sweep.json"
    _write_entry_spec(spec_path)
    output_dir = tmp_path / "out"

    call_order = []
    fake_case_config = mock.Mock(case_id="implicit_TNNP")
    fake_spec = mock.Mock()
    fake_spec.plan_case = None
    fake_spec.case_root = tmp_path / "case_root"
    fake_spec.build_cases.return_value = [fake_case_config]
    fake_spec.apply_case.side_effect = lambda *a, **k: call_order.append("apply_case")

    fake_report = mock.Mock()
    fake_report.status = "ok"

    def fake_to_json():
        # Realistic entry-mode path: the tutorial's own case_root/output_dir_name
        # tree, which is NOT a subdirectory of the sweep's own --output-dir --
        # found via a real (non-mocked) sweep-run: relative_to(output_dir)
        # raised ValueError because these are two unrelated directory trees.
        state_dir = fake_spec.case_root / f"state_{len(call_order)}"
        return {"status": "ok", "run_document": {"version": "3", "launch": {"caseRoot": str(fake_spec.case_root), "outputDir": str(state_dir)}}}
    fake_report.to_json.side_effect = fake_to_json

    def fake_subprocess_run(cmd, **kwargs):
        call_order.append("run")
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.load_entry_spec", return_value=fake_spec), \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run):
        result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    assert call_order == ["apply_case", "run", "apply_case", "run"]
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert result["postprocess"]["status"] == "not_configured"


def test_sweep_run_archives_each_case_postprocessing_output_when_configured(tmp_path):
    # base.archive_dir_name opts an entry-mode sweep into the generic
    # snapshot/diff collection (output_collection.py): real bug this
    # reproduces -- some workflow_dags have no "clean" step, so
    # case_root/postProcessing/ persists and accumulates across sequential
    # cases sharing one case_root. Each case's own new/changed file must land
    # inside that case's own output_dir_name folder (workflow_state_path's
    # parent, the same directory workflow_state.json lives in) under
    # <archive_dir_name>/, distinctly, without needing the tutorial's own
    # bespoke staging code or a separate cache location.
    spec_path = tmp_path / "sweep.json"
    spec = {
        "base": {"entry": "sampleTutorial", "archive_dir_name": "sweepCases"},
        "sweep": {
            "mode": "cross_product",
            "independent": {"dx_values": [[0.5], [0.2]]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["dx_values"]}],
        },
    }
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"
    case_root = tmp_path / "case_root"
    (case_root / "postProcessing").mkdir(parents=True)

    call_order = []
    case_output_dirs: dict[int, Path] = {}
    fake_case_config = mock.Mock(case_id="dx0.5")
    fake_spec = mock.Mock()
    fake_spec.plan_case = None
    fake_spec.case_root = case_root
    fake_spec.build_cases.return_value = [fake_case_config]
    fake_spec.apply_case.side_effect = lambda *a, **k: call_order.append("apply_case")

    fake_report = mock.Mock()
    fake_report.status = "ok"

    def fake_to_json():
        state_dir = case_root / f"state_{len(call_order)}"
        return {"status": "ok", "run_document": {"version": "3", "launch": {"caseRoot": str(case_root), "outputDir": str(state_dir)}}}
    fake_report.to_json.side_effect = fake_to_json

    def fake_subprocess_run(cmd, **kwargs):
        call_order.append("run")
        n = len([c for c in call_order if c == "run"])
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        output_dir_for_case = Path(run_doc["launch"]["outputDir"])
        case_output_dirs[n] = output_dir_for_case
        workflow_state_path = output_dir_for_case / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        # Simulate the solver writing this case's own deterministically-named
        # output into the SHARED case_root's postProcessing/ dir.
        (case_root / "postProcessing" / f"case_{n}.dat").write_text(f"result {n}")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.load_entry_spec", return_value=fake_spec), \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run):
        result = sweep_run(spec_path, output_dir=output_dir, driver_context=_POSTPROCESSING_CTX)

    assert result["completed_count"] == 2
    # Each case's archived output lands inside that case's own output_dir --
    # the same directory workflow_state.json lives in -- not a separate
    # shared cache keyed by case_id.
    assert (case_output_dirs[1] / "sweepCases" / "case_1.dat").read_text() == "result 1"
    assert (case_output_dirs[2] / "sweepCases" / "case_2.dat").read_text() == "result 2"
    assert case_output_dirs[1] != case_output_dirs[2]


def test_sweep_run_archives_each_case_postprocessing_output_by_default(tmp_path):
    # Same setup as test_sweep_run_archives_each_case_postprocessing_output_when_configured,
    # but the spec does NOT supply base.archive_dir_name -- archival must still
    # happen, using the built-in default name, not be skipped entirely.
    spec_path = tmp_path / "sweep.json"
    spec = {
        "base": {"entry": "sampleTutorial"},
        "sweep": {
            "mode": "cross_product",
            "independent": {"dx_values": [[0.5], [0.2]]},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["dx_values"]}],
        },
    }
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"
    case_root = tmp_path / "case_root"
    (case_root / "postProcessing").mkdir(parents=True)

    call_order = []
    case_output_dirs: dict[int, Path] = {}
    fake_case_config = mock.Mock(case_id="dx0.5")
    fake_spec = mock.Mock()
    fake_spec.plan_case = None
    fake_spec.case_root = case_root
    fake_spec.build_cases.return_value = [fake_case_config]
    fake_spec.apply_case.side_effect = lambda *a, **k: call_order.append("apply_case")

    fake_report = mock.Mock()
    fake_report.status = "ok"

    def fake_to_json():
        state_dir = case_root / f"state_{len(call_order)}"
        return {"status": "ok", "run_document": {"version": "3", "launch": {"caseRoot": str(case_root), "outputDir": str(state_dir)}}}
    fake_report.to_json.side_effect = fake_to_json

    def fake_subprocess_run(cmd, **kwargs):
        call_order.append("run")
        n = len([c for c in call_order if c == "run"])
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        output_dir_for_case = Path(run_doc["launch"]["outputDir"])
        case_output_dirs[n] = output_dir_for_case
        workflow_state_path = output_dir_for_case / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        (case_root / "postProcessing" / f"case_{n}.dat").write_text(f"result {n}")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.load_entry_spec", return_value=fake_spec), \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run):
        result = sweep_run(spec_path, output_dir=output_dir, driver_context=_POSTPROCESSING_CTX)

    assert result["completed_count"] == 2
    assert (case_output_dirs[1] / "collectedOutput" / "case_1.dat").read_text() == "result 1"
    assert (case_output_dirs[2] / "collectedOutput" / "case_2.dat").read_text() == "result 2"


def test_sweep_plan_refuses_over_cap_without_expanding(tmp_path):
    spec = {
        "base": {"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
                 "physics_selectors": {"type": "electroModel"}},
        "sweep": {"mode": "cross_product", "independent": {"a": list(range(20)), "b": list(range(20))}, "dependent": []},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))

    with mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize:
        with pytest.raises(SweepValidationError):
            sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)
    mock_materialize.assert_not_called()


def test_sweep_run_refuses_over_cap_without_expanding(tmp_path):
    spec = {
        "base": {"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
                 "physics_selectors": {"type": "electroModel"}},
        "sweep": {"mode": "cross_product", "independent": {"a": list(range(20)), "b": list(range(20))}, "dependent": []},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))

    with mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run") as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        with pytest.raises(SweepValidationError):
            sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)
    mock_materialize.assert_not_called()
    mock_run.assert_not_called()


def test_sweep_run_accepts_over_cap_with_explicit_override(tmp_path):
    spec = {
        "base": {"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
                 "physics_selectors": {"type": "electroModel"}},
        "sweep": {"mode": "cross_product", "independent": {"modelName": ["TNNP"] * 250}, "dependent": []},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output_dir = tmp_path / "out"

    def fake_materialize(*, case_dir, routed, driver_context):
        # sweep_runner threads its context into materialize_case (Part B of
        # the 2026-09-02 neutral-default spec); a double that refused the
        # kwarg would fail for the wrong reason.
        del driver_context
        case_dir.mkdir(parents=True, exist_ok=True)

    fake_report = mock.Mock()
    fake_report.status = "ok"
    fake_report.to_json.return_value = {
        "status": "ok",
        "run_document": {
            "version": "3",
            "launch": {"outputDir": str(output_dir / "dummy" / "postProcessing")},
        },
    }

    with mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case", side_effect=fake_materialize), \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run"):
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, max_cases=300, driver_context=_CTX)
    assert result["case_count"] == 250


def test_resume_skips_terminal_completed_case(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    spec = json.loads(spec_path.read_text())
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    from omnidriver.core.runtime.sweep_manifest import (
        CaseManifestEntry, SweepManifest, compute_spec_hash, write_manifest,
    )
    case_dir = output_dir / "x"
    state_dir = case_dir / "postProcessing"
    state_dir.mkdir(parents=True)
    (state_dir / "workflow_state.json").write_text('{"status": "completed"}')
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(spec),
        created_at="t0", updated_at="t0",
        cases=[CaseManifestEntry(
            case_id="x", resolved_axis_values={"param": "x"},
            override_hash="sha256:x", run_document_path="x/run_document.json",
            workflow_state_path="x/postProcessing/workflow_state.json",
            status="completed", outcome="fresh", started_at="t0", updated_at="t0",
        )],
    )
    write_manifest(output_dir / "sweep_manifest.json", manifest)

    # sweep_run calls route_case_values() unconditionally for every case,
    # before prior_status is ever consulted (see sweep_runner.py's
    # "routed = route_case_values(...)" ahead of the "elif prior_status ==
    # 'completed'" branch) -- so a real plugin's routing catalog would
    # otherwise be reached here even though this test is about resume
    # bookkeeping, not routing. Mocked because nothing below asserts on what
    # `routed` contains.
    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner._completed_case_is_reusable", return_value=(True, None)), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run") as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)

    mock_materialize.assert_not_called()
    mock_run.assert_not_called()
    assert result["skipped_count"] == 1


def test_fresh_reruns_case_reported_as_completed_and_wipes_stray_files(tmp_path):
    # Mirrors test_resume_skips_terminal_completed_case, but with fresh=True:
    # this reproduces the 2026-08-05 incident (a case directory whose
    # workflow_state.json says "completed" from a previous session was
    # silently reported as fresh) and asserts --fresh actually reruns it and
    # wipes the whole output_dir, not just the state file.
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    spec = json.loads(spec_path.read_text())
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    from omnidriver.core.runtime.sweep_manifest import (
        CaseManifestEntry, SweepManifest, compute_spec_hash, write_manifest,
    )
    case_dir = output_dir / "x"
    state_dir = case_dir / "postProcessing"
    state_dir.mkdir(parents=True)
    (state_dir / "workflow_state.json").write_text('{"status": "completed"}')
    stray_path = output_dir / "stray_from_previous_run.txt"
    stray_path.write_text("should be wiped by --fresh")
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(spec),
        created_at="t0", updated_at="t0",
        cases=[CaseManifestEntry(
            case_id="x", resolved_axis_values={"param": "x"},
            override_hash="sha256:x", run_document_path="x/run_document.json",
            workflow_state_path="x/postProcessing/workflow_state.json",
            status="completed", outcome="fresh", started_at="t0", updated_at="t0",
        )],
    )
    write_manifest(output_dir / "sweep_manifest.json", manifest)

    fake_report = mock.Mock()
    fake_report.status = "ok"
    fake_report.to_json.return_value = {
        "status": "ok",
        "run_document": {"version": "3", "launch": {"outputDir": str(state_dir)}},
    }

    def fake_subprocess_run(cmd, **kwargs):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "workflow_state.json").write_text('{"status": "completed"}')
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner._completed_case_is_reusable", return_value=(True, None)), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run) as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, fresh=True, driver_context=_CTX)

    mock_materialize.assert_called_once()
    mock_run.assert_called_once()
    assert result["completed_count"] == 1
    assert not stray_path.exists()
    by_id = {case["case_id"]: case for case in result["cases"]}
    assert by_id["x"]["outcome"] != "skipped"


def test_fresh_defaults_to_false_and_preserves_resume_behavior(tmp_path):
    # Regression guard: omitting fresh (or passing fresh=False) must keep the
    # existing skip-if-completed behavior exactly as test_resume_skips_
    # terminal_completed_case already verifies -- this just re-asserts it
    # with fresh explicitly passed as False, at the new call signature.
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    spec = json.loads(spec_path.read_text())
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    from omnidriver.core.runtime.sweep_manifest import (
        CaseManifestEntry, SweepManifest, compute_spec_hash, write_manifest,
    )
    case_dir = output_dir / "x"
    state_dir = case_dir / "postProcessing"
    state_dir.mkdir(parents=True)
    (state_dir / "workflow_state.json").write_text('{"status": "completed"}')
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(spec),
        created_at="t0", updated_at="t0",
        cases=[CaseManifestEntry(
            case_id="x", resolved_axis_values={"param": "x"},
            override_hash="sha256:x", run_document_path="x/run_document.json",
            workflow_state_path="x/postProcessing/workflow_state.json",
            status="completed", outcome="fresh", started_at="t0", updated_at="t0",
        )],
    )
    write_manifest(output_dir / "sweep_manifest.json", manifest)

    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner._completed_case_is_reusable", return_value=(True, None)), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run") as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, fresh=False, driver_context=_CTX)

    mock_materialize.assert_not_called()
    mock_run.assert_not_called()
    assert result["skipped_count"] == 1


def test_resume_leaves_terminal_failed_alone_without_retry_flag(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    spec = json.loads(spec_path.read_text())
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    from omnidriver.core.runtime.sweep_manifest import (
        CaseManifestEntry, SweepManifest, compute_spec_hash, write_manifest,
    )
    case_dir = output_dir / "x"
    state_dir = case_dir / "postProcessing"
    state_dir.mkdir(parents=True)
    (state_dir / "workflow_state.json").write_text('{"status": "failed"}')
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(spec),
        created_at="t0", updated_at="t0",
        cases=[CaseManifestEntry(
            case_id="x", resolved_axis_values={"param": "x"},
            override_hash="sha256:x", run_document_path="x/run_document.json",
            workflow_state_path="x/postProcessing/workflow_state.json",
            status="failed", outcome="fresh", started_at="t0", updated_at="t0",
        )],
    )
    write_manifest(output_dir / "sweep_manifest.json", manifest)

    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run") as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, retry_failed=False, driver_context=_CTX)

    mock_materialize.assert_not_called()
    mock_run.assert_not_called()
    assert result["failed_count"] == 1


def test_resume_retries_terminal_failed_case_with_retry_flag(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    spec = json.loads(spec_path.read_text())
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    from omnidriver.core.runtime.sweep_manifest import (
        CaseManifestEntry, SweepManifest, compute_spec_hash, write_manifest,
    )
    case_dir = output_dir / "x"
    state_dir = case_dir / "postProcessing"
    state_dir.mkdir(parents=True)
    (state_dir / "workflow_state.json").write_text('{"status": "failed"}')
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(spec),
        created_at="t0", updated_at="t0",
        cases=[CaseManifestEntry(
            case_id="x", resolved_axis_values={"param": "x"},
            override_hash="sha256:x", run_document_path="x/run_document.json",
            workflow_state_path="x/postProcessing/workflow_state.json",
            status="failed", outcome="fresh", started_at="t0", updated_at="t0",
        )],
    )
    write_manifest(output_dir / "sweep_manifest.json", manifest)

    fake_report = mock.Mock()
    fake_report.status = "ok"
    fake_report.to_json.return_value = {
        "status": "ok",
        "run_document": {"version": "3", "launch": {"outputDir": str(state_dir)}},
    }

    def fake_subprocess_run(cmd, **kwargs):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "workflow_state.json").write_text('{"status": "completed"}')
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case") as mock_materialize, \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run) as mock_run:
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, retry_failed=True, driver_context=_CTX)

    mock_materialize.assert_called_once()
    mock_run.assert_called_once()
    assert result["completed_count"] == 1
    assert result["failed_count"] == 0
    by_id = {case["case_id"]: case for case in result["cases"]}
    assert by_id["x"]["outcome"] == "retried"
    assert by_id["x"]["status"] == "completed"


def test_sweep_run_case_timeout_marks_failed_and_continues(tmp_path):
    # A case whose run subprocess exceeds case_timeout_s must be recorded as a
    # per-case failure (not crash the whole sweep), and the timeout must be
    # passed through to the owned case-process launcher.
    spec_path = tmp_path / "sweep.json"
    _write_placeholder_spec(spec_path)
    output_dir = tmp_path / "out"

    def fake_materialize(*, case_dir, routed, driver_context):
        # sweep_runner threads its context into materialize_case (Part B of
        # the 2026-09-02 neutral-default spec); a double that refused the
        # kwarg would fail for the wrong reason.
        del driver_context
        case_dir.mkdir(parents=True, exist_ok=True)

    fake_report = mock.Mock()
    fake_report.status = "ok"
    fake_report.to_json.return_value = {
        "status": "ok",
        "run_document": {
            "version": "3",
            "launch": {"outputDir": str(output_dir / "x" / "postProcessing")},
        },
    }

    seen_kwargs = {}

    def fake_case_process(cmd, **kwargs):
        seen_kwargs.update(kwargs)
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    with mock.patch("omnidriver.core.runtime.sweep_runner.route_case_values", return_value={}), \
         mock.patch("omnidriver.core.runtime.sweep_runner.materialize_case", side_effect=fake_materialize), \
         mock.patch("omnidriver.core.runtime.sweep_runner.strict_plan", return_value=fake_report), \
         mock.patch("omnidriver.core.runtime.sweep_runner._run_case_process", side_effect=fake_case_process):
        from omnidriver.core.runtime.sweep_runner import sweep_run
        result = sweep_run(spec_path, output_dir=output_dir, case_timeout_s=0.01, driver_context=_CTX)

    assert seen_kwargs.get("timeout") == 0.01
    assert result["failed_count"] == 1
    assert result["completed_count"] == 0
    by_id = {case["case_id"]: case for case in result["cases"]}
    assert by_id["x"]["status"] == "failed"
    assert "timeout" in by_id["x"]["timeout_error"].lower()
    # sweep stayed resumable: manifest was still written
    assert (output_dir / "sweep_manifest.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="process-group ownership is POSIX-only")
def test_sweep_case_timeout_kills_term_ignoring_descendant(tmp_path):
    pid_file = tmp_path / "sweep-child.pid"
    child_code = (
        "import os, pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(30)"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        _run_case_process(
            [sys.executable, "-c", parent_code],
            env=dict(os.environ),
            timeout=1,
        )

    assert pid_file.exists(), "fixture child did not install its SIGTERM handler"
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2

    def pid_exists() -> bool:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    try:
        while time.monotonic() < deadline and pid_exists():
            time.sleep(0.02)
        assert not pid_exists(), "timed-out sweep descendant survived cleanup"
    finally:
        if pid_exists():
            os.kill(child_pid, signal.SIGKILL)


def test_spec_hash_mismatch_is_refused(tmp_path):
    spec_path = tmp_path / "sweep.json"
    _write_spec(spec_path, models=("TNNP",))
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    from omnidriver.core.runtime.sweep_manifest import SweepManifest, write_manifest
    write_manifest(
        output_dir / "sweep_manifest.json",
        SweepManifest(schema_version="1.0", sweep_spec_hash="sha256:stale", created_at="t0", updated_at="t0", cases=[]),
    )
    from omnidriver.core.runtime.sweep_runner import sweep_run
    with pytest.raises(SweepValidationError, match="hash|spec changed"):
        sweep_run(spec_path, output_dir=output_dir, driver_context=_CTX)


# ---------------------------------------------------------------------------
# Item 2: a study whose "entry" names a tutorial record dispatches through
# _record_sweep_plan/_record_sweep_run, never the factory-entry path.
# ---------------------------------------------------------------------------


from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.tutorial_records import (
    AxisContract,
    AxisPatch,
    AxisResult,
    TutorialRecord,
    TutorialRecordError,
    WorkflowStep,
)
from plugins.minimal_plugin import MinimalTestPlugin


def _record_deep_set(node: dict, key_path: list, value: str) -> None:
    for segment in key_path[:-1]:
        node = node.setdefault(segment, {})
    node[key_path[-1]] = value


def _record_known_catalog_validator(document: str, key_path: tuple, value):
    catalog = {("constant/mesh.json", ("cells",)): "integer"}
    if (document, key_path) in catalog:
        return catalog[(document, key_path)], True
    raise KeyError(f"{document}:{'.'.join(key_path)} not in this test's catalog")


def _record_read_current_value(document_path: Path, key_path: tuple):
    """Mirror the real reader's contract: a KEY-PATH TUPLE in, the current
    value (or None) out -- matching test_tutorial_records.py's own toy
    reader. Needed so this file's own "committed"/"unchanged" assertions
    (M1) prove a real change from a real no-op, rather than relying on
    split_unchanged's "no reader -> report everything changed" default."""
    if not document_path.exists():
        return None
    node = json.loads(document_path.read_text())
    *scope, key = key_path
    for segment in scope:
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    if not isinstance(node, dict) or key not in node:
        return None
    return node[key]


def _record_typed_agree(value_kind: str, requested, current) -> bool:
    if current is None:
        return False
    try:
        if value_kind == "integer":
            return int(requested) == int(current)
    except (TypeError, ValueError):
        return False
    return str(requested) == str(current)


def _record_number_cells_axis() -> AxisContract:
    def resolve(value, staged_case_root):
        return AxisResult(
            patches=(
                AxisPatch(
                    document="constant/mesh.json", key_path=("cells",),
                    value=int(value), value_kind="integer",
                ),
            ),
        )

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


class _RecordSweepWriterPlugin(MinimalTestPlugin):
    """A toy JSON case_writer, matching test_tutorial_records.py's
    ``_RecordCaseWriterPlugin`` -- duplicated locally rather than imported to
    keep this file's existing zero-cardiac-dependency test isolation."""

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {
                "qualified_id": p.qualified_id,
                "document": p.document,
                "expanded_key_path": list(p.expanded_key_path()),
                "value": p.value,
                "format": "sweep_test_json",
            }
            for p in request.parameters
        )
        expected_effects = tuple(
            f"set {p.qualified_id} in {p.document}" for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets, preconditions=(),
            expected_effects=expected_effects, semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({"sweep_test_json"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        by_document: dict = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], []).append(target)
        rendered = []
        for document, targets in by_document.items():
            path = Path(snapshot_root) / document
            exists_before = path.exists()
            before_digest = _digest_bytes(path.read_bytes()) if exists_before else None
            content_obj = json.loads(path.read_text()) if exists_before else {}
            for target in targets:
                _record_deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            content = (json.dumps(content_obj, sort_keys=True) + "\n").encode()
            rendered.append(RenderedFile(
                path=document, content=content, mode=None,
                exists_before=exists_before, before_digest=before_digest,
                renderer_id=self.plugin_id, format="sweep_test_json",
            ))
        return tuple(rendered)

    def get_case_value_comparator(self):
        return _record_typed_agree

    def get_config_value_reader(self):
        return _record_read_current_value


def _toy_record() -> TutorialRecord:
    return TutorialRecord(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        allowed_axes=frozenset({"number_cells"}),
        workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker")),),
    )


def _native_toy_case(tmp_path: Path) -> Path:
    native = tmp_path / "native" / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1"}))
    return native.parent


def _record_sweep_spec(*, cases_root: Path, values=(2, 3)) -> dict:
    return {
        "base": {"entry": "toyTutorial", "cases_root": str(cases_root)},
        "sweep": {
            "mode": "cross_product",
            "independent": {"number_cells": list(values)},
            "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["number_cells"]}],
        },
    }


def _record_driver_context():
    plugin = _RecordSweepWriterPlugin(
        solver_commands=frozenset({"touch"}),
        tutorial_records={"toyTutorial": _toy_record()},
        axis_catalog={"number_cells": _record_number_cells_axis()},
        record_key_validator=_record_known_catalog_validator,
    )
    return _driver_context(plugin, source="test:record-sweep")


def test_sweep_plan_over_a_record_entry_refuses_a_bad_axis_name_upfront_before_staging_any_case(tmp_path):
    """Minor: study-name/capability refusals happen ONCE, up front, for the
    whole sweep -- before this fix, a bad axis name reached
    resolve_case_patches independently for every case, each staging its own
    case directory before failing. Confirmed here: NO case directory exists
    after the refusal, for a 2-case sweep."""
    cases_root = _native_toy_case(tmp_path)
    spec = _record_sweep_spec(cases_root=cases_root)
    spec["sweep"]["independent"]["not_a_real_axis"] = [1, 2]
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    ctx = _record_driver_context()

    with pytest.raises(TutorialRecordError, match="not_a_real_axis"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert not (tmp_path / "out" / "cases").exists()


def test_sweep_run_over_a_record_entry_refuses_a_missing_capability_upfront_before_staging_any_case(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    plugin = _RecordSweepWriterPlugin(
        solver_commands=frozenset({"touch"}),
        tutorial_records={"toyTutorial": _toy_record()},
        axis_catalog={"number_cells": _record_number_cells_axis()},
        record_key_validator=None,  # no validator declared at all
    )
    ctx = _driver_context(plugin, source="test:record-sweep-no-validator")

    with pytest.raises(TutorialRecordError, match="no record-key validator"):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert not (tmp_path / "out").exists()


def test_sweep_plan_over_a_record_entry_previews_every_case_without_running(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "ok", case
        assert case["record_commit_status"] == "committed"
    # sweep-plan never runs the workflow -- only strict_plan's non-mutating
    # report, matching the factory-entry branch's own contract.
    assert not any((tmp_path / "out" / case["case_id"] / "solved.marker").exists()
                    for case in result["cases"])


def test_sweep_plan_over_a_record_entry_persists_unchanged_patches_per_case(tmp_path):
    """M5-of-2a: a patch that already matched the case (native cells="1",
    swept number_cells=1) is real per-case information -- persisted in the
    sweep summary, not discarded the moment commit_record_case returns."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(1, 3))))
    ctx = _record_driver_context()

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    by_case_id = {c["case_id"]: c for c in result["cases"]}
    noop_case = by_case_id["1"]
    assert [p["value"] for p in noop_case["unchanged_patches"]] == [1]
    assert noop_case["unchanged_patches"][0]["status"] == "unchanged"
    changed_case = by_case_id["3"]
    assert changed_case["unchanged_patches"] == []


def test_sweep_run_over_a_record_entry_persists_unchanged_patches_in_the_manifest(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(1,))))
    ctx = _record_driver_context()

    def fake_subprocess_run(cmd, **kwargs):
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        case_root = Path(run_doc["launch"]["caseRoot"])
        (case_root / "solved.marker").write_text("")
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch(
        "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
    ):
        result = sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert [p["value"] for p in result["cases"][0]["unchanged_patches"]] == [1]

    manifest = json.loads((tmp_path / "out" / "sweep_manifest.json").read_text())
    assert [p["value"] for p in manifest["cases"][0]["unchanged_patches"]] == [1]


def test_sweep_plan_over_a_record_entry_refuses_without_cases_root(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec = _record_sweep_spec(cases_root=cases_root)
    del spec["base"]["cases_root"]
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    ctx = _record_driver_context()

    with pytest.raises(TutorialRecordError, match="cases_root"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_run_over_a_record_entry_commits_and_runs_two_cases(tmp_path):
    """Item 2's own end-to-end shape: a 2-case record study gets exactly one
    commit_record_case per case, and the record's workflow steps run through
    the same run-document/workflow-runner machinery a factory entry uses.

    The spawned ``omnidriver run --run-document`` subprocess is faked here
    the same way this suite's OWN factory-entry equivalent
    (``test_sweep_run_entry_mode_executes_run_document_sequentially``) and
    cardiacfoam's ``test_sweep_run_writes_run_documents_and_continues_past_
    failure`` both already do: a fresh ``python -m omnidriver run
    --run-document`` process resolves its plugin via ``--plugin``/entry-point
    default resolution, never the in-process ``driver_context`` a test
    builds, so asserting the CHILD PROCESS'S OWN observable behavior (which
    run-document path it was given, that it's the one this sweep just built)
    is what a fake can prove; a real spawn is exercised separately (manual
    CLI proof, see this task's report)."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()

    commits = []
    real_commit_record_case = __import__(
        "omnidriver.core.runtime.record_execution", fromlist=["commit_record_case"],
    ).commit_record_case

    def tracking_commit(*args, **kwargs):
        result = real_commit_record_case(*args, **kwargs)
        commits.append(result)
        return result

    def fake_subprocess_run(cmd, **kwargs):
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        assert run_doc["workflowDag"]["steps"][0]["command"] == "touch"
        assert run_doc["workflowDag"]["steps"][0]["args"] == ["solved.marker"]
        case_root = Path(run_doc["launch"]["caseRoot"])
        (case_root / "solved.marker").write_text("")
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch(
        "omnidriver.core.runtime.sweep_runner.commit_record_case", side_effect=tracking_commit,
    ), mock.patch(
        "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
    ):
        result = sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert result["case_count"] == 2
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert len(commits) == 2
    assert {c.write_record.transaction_id for c in commits if c.write_record} .__len__() == 2
    for case in result["cases"]:
        assert case["status"] == "completed"
        assert case["record_commit_status"] == "committed"
        staged_case_root = tmp_path / "out" / "cases" / case["case_id"]
        assert (staged_case_root / "solved.marker").exists()
        assert json.loads((staged_case_root / "constant" / "mesh.json").read_text())["cells"] in ("2", "3")


def test_sweep_run_refuses_retry_failed_for_a_record_entry(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()

    with pytest.raises(TutorialRecordError, match="retry-failed"):
        sweep_run(
            spec_path, output_dir=tmp_path / "out", retry_failed=True, driver_context=ctx,
        )


def test_sweep_run_over_a_record_entry_refuses_to_resume_an_existing_manifest(tmp_path):
    """B2: a record-entry sweep does not support resume -- re-running
    sweep_run against an output directory that already holds a manifest
    (and no --fresh) must refuse by name rather than silently restage and
    rerun every case from scratch."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()

    def fake_subprocess_run(cmd, **kwargs):
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        case_root = Path(run_doc["launch"]["caseRoot"])
        (case_root / "solved.marker").write_text("")
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch(
        "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
    ):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    with pytest.raises(TutorialRecordError, match="does not support resume"):
        with mock.patch(
            "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
        ):
            sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_run_over_a_record_entry_refuses_a_changed_spec_against_the_same_output_dir(tmp_path):
    """B2's spec-hash half: the same 'sweep.json changed' refusal the
    factory branch already gives, reused here rather than silently accepting
    the new spec and leaving stale case directories from the old one."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3))))
    ctx = _record_driver_context()

    def fake_subprocess_run(cmd, **kwargs):
        run_doc_path = Path(cmd[cmd.index("--run-document") + 1])
        run_doc = json.loads(run_doc_path.read_text())
        case_root = Path(run_doc["launch"]["caseRoot"])
        (case_root / "solved.marker").write_text("")
        workflow_state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
        workflow_state_path.parent.mkdir(parents=True, exist_ok=True)
        workflow_state_path.write_text(json.dumps({"status": "completed"}))
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch(
        "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
    ):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(4,))))
    with pytest.raises(SweepValidationError, match="hash mismatch"):
        with mock.patch(
            "omnidriver.core.runtime.sweep_runner.subprocess.run", side_effect=fake_subprocess_run,
        ):
            sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_plan_over_a_record_entry_resolves_a_relative_output_dir(tmp_path, monkeypatch):
    """M4: a relative --output-dir used to reach commit_record_case
    unresolved (`case_root must be absolute`) -- resolved before staging,
    matching the factory branch's own CLI-resolved --output-dir."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()
    monkeypatch.chdir(tmp_path)

    result = sweep_plan(spec_path, output_dir=Path("relout"), driver_context=ctx)

    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "ok", case


def test_sweep_record_is_never_dispatched_for_a_factory_entry(tmp_path):
    """A study naming an ordinary factory tutorial that is NOT in the
    stack's tutorial_records catalog is completely unaffected -- even when
    the same stack registers OTHER, unrelated records -- _sweep_record
    returns (None, None), so sweep_plan/sweep_run fall straight through to
    the unchanged factory-entry branch."""
    from omnidriver.core.runtime.sweep_runner import _sweep_record

    ctx = _record_driver_context()  # registers "toyTutorial" as a record
    spec = {
        "base": {"entry": "someFactoryTutorial"},
        "sweep": {"mode": "cross_product", "independent": {}},
    }
    record, cases_root = _sweep_record(spec, driver_context=ctx)
    assert record is None
    assert cases_root is None


def test_sweep_record_refuses_when_shadowed_by_a_cwd_case_path(tmp_path, monkeypatch):
    """B1/M6: `_sweep_record` used to carry only a duplicated copy of the
    record-vs-factory ambiguity check, missing the record-vs-cwd-case-path
    one `resolve_entry`/`describe` already refuse -- a sweep over a record
    name shadowed by a real case directory under cwd used to silently run
    the record. Both now share one classifier (`registry.classify_entry`)."""
    cases_root = _native_toy_case(tmp_path)
    plugin = _RecordSweepWriterPlugin(
        solver_commands=frozenset({"touch"}),
        tutorial_records={"toyTutorial": _toy_record()},
        axis_catalog={"number_cells": _record_number_cells_axis()},
        record_key_validator=_record_known_catalog_validator,
        entrypoint="run-test-case",
    )
    ctx = _driver_context(plugin, source="test:record-sweep-shadow-cwd")
    cwd = tmp_path / "cwd"
    (cwd / "toyTutorial").mkdir(parents=True)
    (cwd / "toyTutorial" / "run-test-case").write_text("#!/bin/sh\n")
    monkeypatch.chdir(cwd)

    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))

    with pytest.raises(KeyError, match="ambiguous"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_record_refuses_when_shadowed_by_a_case_folder_under_cases_root(tmp_path):
    """B1/M6: the same ambiguity as above, but against a DIFFERENT, same-
    NAMED case folder under the sweep's own `cases_root` (not cwd, and not
    the record's own native case, which sits elsewhere here on purpose --
    see test_sweep_record_does_not_confuse_a_records_own_native_case right
    below for why that one specific case must NOT be flagged). This one was
    never refused ANYWHERE before this fix, not even through
    `resolve_entry`/`describe` directly (`_match_entry`'s own
    tutorial_record exclusion meant a record resolution was returned first,
    the case-folder match never consulted)."""
    cases_root = tmp_path / "cases"
    (cases_root / "nativeCases" / "toyTutorial" / "constant").mkdir(parents=True)
    (cases_root / "nativeCases" / "toyTutorial" / "constant" / "mesh.json").write_text(
        json.dumps({"cells": "1"})
    )
    (cases_root / "toyTutorial").mkdir(parents=True)
    (cases_root / "toyTutorial" / "run-test-case").write_text("#!/bin/sh\n")
    record = TutorialRecord(
        name="toyTutorial",
        native_case_relpath="nativeCases/toyTutorial",
        allowed_axes=frozenset({"number_cells"}),
        workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker")),),
    )
    plugin = _RecordSweepWriterPlugin(
        solver_commands=frozenset({"touch"}),
        tutorial_records={"toyTutorial": record},
        axis_catalog={"number_cells": _record_number_cells_axis()},
        record_key_validator=_record_known_catalog_validator,
        entrypoint="run-test-case",
    )
    ctx = _driver_context(plugin, source="test:record-sweep-shadow-folder")
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))

    with pytest.raises(KeyError, match="ambiguous"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_record_does_not_confuse_a_records_own_native_case(tmp_path):
    """The refinement the test above depends on: a record's OWN native case
    is routinely ALSO independently recognizable as a plain case_folder (a
    real adapter's entrypoint/marker declaration knows its own format, which
    the native case obviously satisfies -- e.g. E2ERecordPlugin's
    has_case_marker checking for its own constant/mesh.json) -- that is the
    SAME directory discovered twice by two different catalogs, not a naming
    collision, and must not block the sweep."""
    cases_root = _native_toy_case(tmp_path)
    ctx = _record_driver_context()
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "ok", case
