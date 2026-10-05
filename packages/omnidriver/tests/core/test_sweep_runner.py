import dataclasses
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from omnidriver.cli import main
from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.planning_types import diagnostic
from omnidriver.core.plugin_interface import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.runtime.attempt_lease import AttemptLeaseError, acquire_case_lease
from omnidriver.core.runtime.process_control import run_child
from omnidriver.core.runtime import sweep_runner
from omnidriver.core.runtime.sweep_runner import SweepStopped, _stage_entry_case, sweep_plan, sweep_run
from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.core.tutorial_records import (
    AxisContract,
    AxisPatch,
    AxisResult,
    TutorialRecord,
    TutorialRecordError,
    WorkflowStep,
)

# Neutral placeholder plugins, not cardiacFoam: this file proves core's own
# sweep bookkeeping (staging, timeout, manifest), not cardiac routing, which
# is tested against the real plugin in the cardiacfoam package.
from plugins.toy import DeclaredCasePlugin
from plugins.toy import QUANTITY_TOY_PLUGIN, ToyProvider, write_quantity_toy_case

_CTX = _driver_context(DeclaredCasePlugin(), source="test:sweep_runner")


class _StagingConventionPlugin(DeclaredCasePlugin):
    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(
            generated_directory_names=("postProcessing", "workflow_logs"),
            generated_file_names=("workflow_state.json",),
            generated_case_markers=("workflow_state.json", "workflow_logs"),
            replica_directory_globs=("processor*",),
            instance_directory_pattern=r"^-?\d+(\.\d+)?(e[+\-]?\d+)?$",
            preserved_instance_names=("0",),
        )


_STAGING_CTX = _driver_context(_StagingConventionPlugin(), source="test:staging")


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


def test_entry_case_staging_restages_after_an_interrupted_promotion(tmp_path, monkeypatch):
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
            and ".omnidriver-candidate" in source_name
            and Path(destination_path) == staged
        ):
            failed = True
            raise OSError("simulated interruption during promotion")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr("omnidriver.core.runtime.sweep_runner.os.replace", interrupt_candidate_promotion)
    with pytest.raises(OSError, match="simulated interruption"):
        _stage_entry_case(source, staged)

    # Staging replaces the whole case, so the next stage needs nothing of the old one.
    assert not staged.exists()
    _stage_entry_case(source, staged)
    assert (staged / "system" / "controlDict").read_text() == "new\n"
    assert not [p for p in staged.parent.glob(".case.omnidriver-*") if "lock" not in p.name]


def test_entry_case_staging_discards_what_a_killed_stage_left_beside_the_case(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "controlDict").write_text("new\n")
    staged = tmp_path / "scratch" / "case"
    staged.mkdir(parents=True)
    for role in ("candidate", "replaced"):
        leftover = staged.parent / f".case.omnidriver-{role}"
        leftover.mkdir()
        (leftover / "half").write_text("x")

    _stage_entry_case(source, staged)

    assert not [p for p in staged.parent.glob(".case.omnidriver-*") if "lock" not in p.name]
    assert (staged / "controlDict").read_text() == "new\n"


def test_case_run_command_forwards_the_selector_the_sweep_was_given():
    from omnidriver.core.plugin_interface import load_plugin_context
    from omnidriver.core.runtime.run_command import omnidriver_run_command

    selector = "plugins.toy:ToyStack"
    command = omnidriver_run_command(
        load_plugin_context(selector), "--run-document", "doc.json",
    )
    assert command == [
        sys.executable, "-m", "omnidriver", "run",
        "--plugin", selector, "--run-document", "doc.json",
    ]


def test_case_run_command_adds_no_selector_a_context_never_had():
    """A hand-built context has no selector; inventing one would be a guess."""
    from omnidriver.core.runtime.run_command import omnidriver_run_command

    command = omnidriver_run_command(_CTX, "--run-document", "doc.json")
    assert "--plugin" not in command


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
        run_child(
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




def _record_deep_set(node: dict, key_path: list, value: str) -> None:
    for segment in key_path[:-1]:
        node = node.setdefault(segment, {})
    node[key_path[-1]] = value


def _record_known_catalog_validator(document: str, key_path: tuple, value):
    catalog = {("constant/mesh.json", ("cells",)): "integer", ("constant/mesh.json", ("label",)): "string"}
    if (document, key_path) in catalog:
        return catalog[(document, key_path)], True
    raise KeyError(f"{document}:{'.'.join(key_path)} not in this test's catalog")


def _record_read_current_value(document_path: Path, key_path: tuple):
    """Mirror the real reader's contract: a KEY-PATH TUPLE in, the current value (or None) out -- matching test_tutorial_records.py's own toy reader."""
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


class _RecordSweepWriterPlugin(ToyProvider):
    """A toy JSON case_writer, matching test_tutorial_records.py's ``_RecordCaseWriterPlugin`` -- duplicated locally rather than imported to keep this file's existing zero-cardiac-dependency test isolation."""

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
            request=request, targets=targets, expected_effects=expected_effects, semantic_owner_id=self.plugin_id,
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

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
        return ()


def _toy_record() -> TutorialRecord:
    return TutorialRecord(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        axes=(_record_number_cells_axis(),),
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
        record_key_validator=_record_known_catalog_validator,
    )
    return _driver_context(plugin, source="test:record-sweep")


def test_sweep_plan_over_a_record_entry_refuses_a_bad_axis_name_upfront_before_staging_any_case(tmp_path):
    """Study-name/capability refusals happen once, up front, for the whole sweep, not per case after staging that case's directory."""
    cases_root = _native_toy_case(tmp_path)
    spec = _record_sweep_spec(cases_root=cases_root)
    spec["sweep"]["independent"]["not_a_real_axis"] = [1, 2]
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    ctx = _record_driver_context()

    with pytest.raises(TutorialRecordError, match="not_a_real_axis"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert not (tmp_path / "out" / "cases").exists()


def test_sweep_run_over_a_record_entry_refuses_a_missing_member_upfront_before_staging_any_case(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    plugin = _RecordSweepWriterPlugin(
        solver_commands=frozenset({"touch"}),
        tutorial_records={"toyTutorial": _toy_record()},
        record_key_validator=None,  # no validator declared at all
    )
    ctx = _driver_context(plugin, source="test:record-sweep-no-validator")

    with pytest.raises(TutorialRecordError, match="get_record_key_validator"):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert not (tmp_path / "out").exists()


def test_a_relative_cases_root_is_read_against_the_repository_root_not_the_working_directory(tmp_path, monkeypatch):
    from dataclasses import replace
    from omnidriver.core.repository import Repository

    _native_toy_case(tmp_path)
    spec_path = tmp_path / "elsewhere" / "sweep.json"
    spec_path.parent.mkdir()
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=Path("native"))))
    context = replace(_record_driver_context(), repository=Repository(
        root=tmp_path, plugin="p", tutorials=tmp_path, source=tmp_path, scripts=tmp_path,
    ))
    monkeypatch.chdir(spec_path.parent)

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=context)

    assert result["case_count"] == 2 and all(case["status"] == "ok" for case in result["cases"])


def test_a_relative_cases_root_with_no_repository_is_refused_by_name(tmp_path):
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=Path("native"))))
    with pytest.raises(TutorialRecordError, match="'native' is relative.*--repo"):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_record_driver_context())


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
    """A patch that already matched the case (native cells="1", swept number_cells=1) is real per-case information -- persisted in the sweep summary, not discarded the moment commit_record_case returns."""
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
        "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
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
    """A 2-case record study gets exactly one commit_and_build_record_spec (stage + commit + spec) per case, and the record's workflow steps run through the same run-document/workflow-runner machinery a factory entry uses."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()

    commits = []
    real_commit_and_build_record_spec = __import__(
        "omnidriver.core.runtime.record_execution",
        fromlist=["commit_and_build_record_spec"],
    ).commit_and_build_record_spec

    def tracking_commit(*args, **kwargs):
        commit_result, spec = real_commit_and_build_record_spec(*args, **kwargs)
        commits.append(commit_result)
        return commit_result, spec

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
        "omnidriver.core.runtime.sweep_runner.commit_and_build_record_spec",
        side_effect=tracking_commit,
    ), mock.patch(
        "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
    ):
        result = sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    assert result["case_count"] == 2
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert len(commits) == 2
    assert all(c.committed for c in commits)
    for case in result["cases"]:
        assert case["status"] == "completed"
        assert case["record_commit_status"] == "committed"
        staged_case_root = tmp_path / "out" / "cases" / case["case_id"]
        assert (staged_case_root / "solved.marker").exists()
        assert json.loads((staged_case_root / "constant" / "mesh.json").read_text())["cells"] in ("2", "3")


def test_sweep_run_over_a_record_entry_refuses_to_resume_an_existing_manifest(tmp_path):
    """A record-entry sweep does not support resume -- re-running sweep_run against an output directory that already holds a manifest (and no --fresh) must refuse by name rather than silently restage and rerun every case from scratch."""
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
        "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
    ):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    with pytest.raises(TutorialRecordError, match="does not resume"):
        with mock.patch(
            "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
        ):
            sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_run_over_a_record_entry_refuses_a_changed_spec_against_the_same_output_dir(tmp_path):
    """The same 'sweep.json changed' refusal the factory branch already gives, reused here rather than silently accepting the new spec and leaving stale case directories from the old one."""
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
        "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
    ):
        sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)

    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(4,))))
    with pytest.raises(SweepValidationError, match="hash mismatch"):
        with mock.patch(
            "omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_subprocess_run,
        ):
            sweep_run(spec_path, output_dir=tmp_path / "out", driver_context=ctx)


def test_sweep_plan_over_a_record_entry_resolves_a_relative_output_dir(tmp_path, monkeypatch):
    """A relative --output-dir is resolved before staging (commit_record_case refuses a relative case_root), matching the factory branch's own CLI-resolved --output-dir."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root)))
    ctx = _record_driver_context()
    monkeypatch.chdir(tmp_path)

    result = sweep_plan(spec_path, output_dir=Path("relout"), driver_context=ctx)

    assert result["case_count"] == 2
    for case in result["cases"]:
        assert case["status"] == "ok", case


def test_sweep_refuses_over_cap_without_staging_any_case(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3, 4))))
    ctx = _record_driver_context()

    with mock.patch("omnidriver.core.runtime.sweep_runner.commit_and_build_record_spec") as commit, \
         mock.patch("omnidriver.core.runtime.sweep_runner.run_child") as run:
        with pytest.raises(SweepValidationError):
            sweep_plan(spec_path, output_dir=tmp_path / "out", max_cases=2, driver_context=ctx)
        with pytest.raises(SweepValidationError):
            sweep_run(spec_path, output_dir=tmp_path / "out", max_cases=2, driver_context=ctx)
    commit.assert_not_called()
    run.assert_not_called()


def test_sweep_accepts_a_case_count_at_the_explicit_cap(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3, 4))))

    result = sweep_plan(spec_path, output_dir=tmp_path / "out", max_cases=3, driver_context=_record_driver_context())

    assert result["case_count"] == 3


@pytest.mark.parametrize("base, message", [
    ({}, "must name the tutorial record"),
    ({"entry": "noSuchRecord", "cases_root": "x"}, "unknown tutorial record 'noSuchRecord'"),
])
def test_a_sweep_must_name_a_registered_record(tmp_path, base, message):
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps({"base": base, "sweep": {"mode": "zip", "independent": {"a": [1]}}}))

    with pytest.raises(TutorialRecordError, match=message):
        sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_record_driver_context())


def test_sweep_run_case_timeout_marks_failed_and_continues(tmp_path):
    """A case whose run subprocess exceeds case_timeout_s is one case's failure, not the sweep's."""
    cases_root = _native_toy_case(tmp_path)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3))))
    output_dir = tmp_path / "out"
    seen_timeouts = []

    def fake_case_process(cmd, **kwargs):
        seen_timeouts.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    with mock.patch("omnidriver.core.runtime.sweep_runner.run_child", side_effect=fake_case_process):
        result = sweep_run(
            spec_path, output_dir=output_dir, case_timeout_s=0.01, driver_context=_record_driver_context(),
        )

    assert seen_timeouts == [0.01, 0.01]
    assert (result["failed_count"], result["completed_count"]) == (2, 0)
    for case in result["cases"]:
        assert case["status"] == "failed"
        assert "timeout" in case["timeout_error"].lower()
    assert (output_dir / "sweep_manifest.json").exists()


def test_sweep_run_child_process_rebuilds_the_parent_context(tmp_path, monkeypatch):
    """Not mocked: each case really runs in a `python -m omnidriver` child."""
    from omnidriver.core.plugin_interface import load_plugin_context
    from plugins.toy import write_toy_native_case

    tests_root = str(Path(__file__).resolve().parents[1])
    inherited = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", tests_root if not inherited else f"{tests_root}{os.pathsep}{inherited}")
    ctx = load_plugin_context("plugins.toy:ToyStack")
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    (tmp_path / "sweep.json").write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3))))
    monkeypatch.chdir(tmp_path)

    result = sweep_run("sweep.json", output_dir="out", driver_context=ctx)

    assert [case["status"] for case in result["cases"]] == ["completed", "completed"], result
    assert result["failed_count"] == 0
    assert (tmp_path / "out" / "cases" / "2" / "solved.marker").is_file()


def _completing_child(cmd, **kwargs):
    run_doc = json.loads(Path(cmd[cmd.index("--run-document") + 1]).read_text())
    state_path = Path(run_doc["launch"]["outputDir"]) / "workflow_state.json"
    state_path.write_text(json.dumps({"status": "completed"}))
    return mock.Mock(returncode=0, stdout="", stderr="")


def _run_toy_sweep(tmp_path, child, *, values=(2, 3)):
    cases_root = _native_toy_case(tmp_path)
    spec = _record_sweep_spec(cases_root=cases_root, values=values)
    spec["base"]["constant/mesh.json:label"] = "base"
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    with mock.patch("omnidriver.core.runtime.sweep_runner.run_child", side_effect=child):
        return sweep_run(
            spec_path, output_dir=tmp_path / "out", driver_context=_record_driver_context(),
        )


def test_a_sweep_case_has_one_folder_holding_its_case_run_document_state_and_record(tmp_path):
    result = _run_toy_sweep(tmp_path, _completing_child)

    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == ["cases", "sweep_manifest.json"]
    for case in result["cases"]:
        folder = out / "cases" / case["case_id"]
        assert case["run_document_path"] == f"cases/{case['case_id']}/run_document.json"
        assert (folder / "run_document.json").is_file()
        record = json.loads((folder / "case_record.json").read_text())
        assert record["case_id"] == case["case_id"]
        assert record["resolved_axis_values"]["number_cells"] in (2, 3)
        assert "status" not in record
        assert (record["run_document_path"], record["workflow_state_path"]) == ("run_document.json", "workflow_state.json")
        document = json.loads((folder / "run_document.json").read_text())
        assert str(folder / "run_document.json") in document["launch"]["command"]


def test_the_manifest_stamps_a_case_before_its_child_starts_and_records_the_base_study(tmp_path):
    seen = []

    def child(cmd, **kwargs):
        manifest = json.loads((tmp_path / "out" / "sweep_manifest.json").read_text())
        seen.append([(c["case_id"], c["sweep_outcome"], c["started_at"] is not None) for c in manifest["cases"]])
        return _completing_child(cmd, **kwargs)

    _run_toy_sweep(tmp_path, child)

    assert seen == [[("2", "running", True)], [("2", "completed", True), ("3", "running", True)]]
    manifest = json.loads((tmp_path / "out" / "sweep_manifest.json").read_text())
    assert manifest["base_study"] == {"constant/mesh.json:label": "base"}
    assert manifest["cli_study"] == {}


def test_a_failed_case_carries_the_childs_reasons_into_its_summary_and_the_manifest_without_the_log_text(tmp_path):
    refusal = {
        "status": "failed", "error": "Execution environment preflight failed.",
        "environment_diagnostics": [{"level": "error", "code": "launcher_mismatch", "message": "wrong MPI"}],
        "failure_context": {
            "step_id": "solve", "attempt": 1, "exit_code": 2, "stdout_log": "logs/solve.out", "stderr_log": "logs/solve.err",
            "diagnostics": [{"code": "solver_entry_missing"}], "stdout_tail": "LONG TAIL", "stderr_tail": "LONG TAIL",
            "stdout_truncated": False, "candidate_remediations": [],
        },
    }

    def child(cmd, **kwargs):
        return mock.Mock(returncode=1, stdout=json.dumps(refusal), stderr="")

    result = _run_toy_sweep(tmp_path, child)

    manifest = json.loads((tmp_path / "out" / "sweep_manifest.json").read_text())
    for case, entry in zip(result["cases"], manifest["cases"]):
        assert case["status"] == "failed"
        for key in ("error", "environment_diagnostics", "failure_context"):
            assert case[key] == refusal[key]
        assert entry["failure"]["error"] == refusal["error"]
        assert entry["failure"]["environment_diagnostics"] == refusal["environment_diagnostics"]
        assert entry["failure"]["failure_context"] == {
            k: refusal["failure_context"][k]
            for k in ("step_id", "attempt", "exit_code", "diagnostics", "stdout_log", "stderr_log")
        }


def test_a_child_that_dies_without_a_report_leaves_its_stderr_tail(tmp_path):
    def child(cmd, **kwargs):
        return mock.Mock(returncode=3, stdout="", stderr="Traceback ...\nSomeError: boom\n")

    result = _run_toy_sweep(tmp_path, child, values=(2,))

    assert "exited 3 without a report" in result["cases"][0]["error"]
    assert "SomeError: boom" in result["cases"][0]["error"]


def test_the_stderr_fallback_of_a_case_is_redacted_with_the_stacks_patterns(tmp_path):
    class Redacting(_RecordSweepWriterPlugin):
        def get_log_redaction_patterns(self):
            return frozenset({r"hunter\d"})

    def child(cmd, **kwargs):
        return mock.Mock(returncode=3, stdout="", stderr="password=hunter2 failed")

    cases_root = _native_toy_case(tmp_path)
    (tmp_path / "sweep.json").write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2,))))
    plugin = Redacting(
        solver_commands=frozenset({"touch"}), tutorial_records={"toyTutorial": _toy_record()},
        record_key_validator=_record_known_catalog_validator,
    )
    with mock.patch("omnidriver.core.runtime.sweep_runner.run_child", side_effect=child):
        result = sweep_run(
            tmp_path / "sweep.json", output_dir=tmp_path / "out", driver_context=_driver_context(plugin, source="test:redact"),
        )

    assert "hunter2" not in result["cases"][0]["error"] and "password=[REDACTED] failed" in result["cases"][0]["error"]


def test_a_plan_that_cannot_run_says_why_in_plan_error(tmp_path):
    real = sweep_runner._strict_plan_for_spec

    def blocked(*args, **kwargs):
        report = real(*args, **kwargs)
        return dataclasses.replace(
            report, status="blocked",
            environment_diagnostics=(diagnostic("error", "launcher_mismatch", "wrong MPI first on PATH"),),
        )

    with mock.patch.object(sweep_runner, "_strict_plan_for_spec", side_effect=blocked):
        result = _run_toy_sweep(tmp_path, _completing_child, values=(2,))

    case = result["cases"][0]
    assert case["status"] == "failed"
    assert case["plan_error"] == "launcher_mismatch: wrong MPI first on PATH"


def test_the_childs_own_record_write_finds_the_sweeps_record_already_in_the_case_folder(tmp_path):
    seen = []

    def child(cmd, **kwargs):
        folder = Path(cmd[cmd.index("--run-document") + 1]).parent
        record = json.loads((folder / "case_record.json").read_text())
        seen.append((record["case_id"], record["resolved_axis_values"]["number_cells"]))
        return _completing_child(cmd, **kwargs)

    _run_toy_sweep(tmp_path, child)

    assert seen == [("2", 2), ("3", 3)]


def _stopped_by_sigterm(cmd, **kwargs):
    run_doc = json.loads(Path(cmd[cmd.index("--run-document") + 1]).read_text())
    Path(run_doc["launch"]["outputDir"], "workflow_state.json").write_text(json.dumps({"status": "failed"}))
    raise SystemExit(143)


def test_a_sweep_stopped_by_a_signal_marks_its_running_case_and_reports(tmp_path):
    cases_root = _native_toy_case(tmp_path)
    (tmp_path / "sweep.json").write_text(json.dumps(_record_sweep_spec(cases_root=cases_root, values=(2, 3, 4))))

    with mock.patch("omnidriver.core.runtime.sweep_runner.run_child", side_effect=_stopped_by_sigterm):
        with pytest.raises(SweepStopped) as stopped:
            sweep_run(tmp_path / "sweep.json", output_dir=tmp_path / "out", driver_context=_record_driver_context())

    assert stopped.value.code == 143
    report = stopped.value.report
    assert (report["case_count"], report["failed_count"], report["skipped_count"]) == (3, 1, 2)
    assert (report["cases"][0]["status"], report["cases"][0]["stopped_by_signal"]) == ("failed", 15)
    manifest = json.loads((tmp_path / "out" / "sweep_manifest.json").read_text())
    assert [(c["case_id"], c["sweep_outcome"]) for c in manifest["cases"]] == [("2", "stopped")]
    assert manifest["cases"][0]["failure"]["stopped_by_signal"] == 15


def test_the_cli_prints_the_report_of_a_sweep_a_signal_stopped(tmp_path, capsys):
    write_quantity_toy_case(tmp_path / "native", "A 0.0015 0 0 0.007\n")
    spec = {"base": {"entry": "toyQuantities", "cases_root": str(tmp_path / "native")},
            "sweep": {"mode": "cross_product", "independent": {"number_cells": [2, 3]}}}
    (tmp_path / "sweep.json").write_text(json.dumps(spec))

    with mock.patch("omnidriver.core.runtime.sweep_runner.run_child", side_effect=_stopped_by_sigterm):
        code = main([
            "sweep-run", "--plugin", QUANTITY_TOY_PLUGIN, "--spec", str(tmp_path / "sweep.json"),
            "--output-dir", str(tmp_path / "out"), "--scratch-dir", str(tmp_path / "scratch"),
        ])

    printed = json.loads(capsys.readouterr().out)
    assert code == 143 and printed["status"] == "failed" and printed["skipped_count"] == 1
