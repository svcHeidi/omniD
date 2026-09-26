from __future__ import annotations

import sys
from pathlib import Path

import pytest

from omnidriver.core.runtime.models import DataArtifact
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


class _ParallelEnvironment(MinimalTestPlugin):
    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(replica_directory_globs=("processor*",))


def _run(root: Path, code: str, *, pattern: str = "result", optional: bool = False,
         instance_indexed: bool = False, driver_context=None) -> dict:
    dag = {
        "schema_version": "1",
        "steps": [{"id": "run", "command": sys.executable, "args": ["-c", code],
                   "cwd": ".", "depends_on": [], "produces": ["output"],
                   "consumes": [], "retry_policy": {"max_attempts": 1}}],
    }
    state = initial_workflow_state(dag)
    assert state is not None
    return run_workflow_step(
        dag, state, "run", case_root=root, log_dir=root / "logs",
        expected_artifacts=(DataArtifact(artifact_id="output", path_pattern=pattern,
                                        format="text", optional=optional,
                                        instance_indexed=instance_indexed),),
        driver_context=driver_context,
    ).state.to_json()


def test_unchanged_required_output_fails(tmp_path: Path) -> None:
    (tmp_path / "result").write_text("old")
    result = _run(tmp_path, "pass")
    assert result["status"] == "failed"
    step = result["steps"][0]
    assert step["exit_code"] == 0
    assert step["produced_artifacts"] == []
    assert {item["code"] for item in step["diagnostics"]} == {"stale_artifacts"}


@pytest.mark.parametrize("preexisting", [False, True])
def test_new_or_same_content_rewritten_output_passes(tmp_path: Path, preexisting: bool) -> None:
    if preexisting:
        (tmp_path / "result").write_text("same")
    result = _run(tmp_path, "from pathlib import Path; Path('result').write_text('same')")
    assert result["status"] == "completed"


def test_optional_unchanged_output_passes(tmp_path: Path) -> None:
    (tmp_path / "result").write_text("old")
    assert _run(tmp_path, "pass", optional=True)["status"] == "completed"


@pytest.mark.parametrize("rewrite", [False, True])
def test_directory_contract_tracks_nested_file_changes(tmp_path: Path, rewrite: bool) -> None:
    nested = tmp_path / "result" / "nested"
    nested.mkdir(parents=True)
    (nested / "file").write_text("same")
    code = "from pathlib import Path; Path('result/nested/file').write_text('same')" if rewrite else "pass"
    result = _run(tmp_path, code)
    assert result["status"] == ("completed" if rewrite else "failed")
    if not rewrite:
        assert result["steps"][0]["diagnostics"][0]["code"] == "stale_artifacts"


@pytest.mark.parametrize("location", ["0.1", "processor0/0.1"])
def test_unchanged_time_output_is_stale_in_both_locations(tmp_path: Path, location: str) -> None:
    directory = tmp_path / location
    directory.mkdir(parents=True)
    (directory / "field").write_text("old")
    context = (
        driver_context(_ParallelEnvironment(), source="test:parallel")
        if location.startswith("processor") else None
    )
    result = _run(
        tmp_path, "pass", pattern="{instance}/field", instance_indexed=True,
        driver_context=context,
    )
    assert result["status"] == "failed"
    assert result["steps"][0]["diagnostics"][0]["code"] == "stale_artifacts"
