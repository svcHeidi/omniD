from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

from omnidriver.core.runtime.models import DataArtifact
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from plugins.minimal_plugin import MinimalTestPlugin


class _ParallelOutputPlugin(MinimalTestPlugin):
    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(decomposition_directory_prefix="processor")


def _dag(command: str, args: list[str], *, produces: list[str] | None = None) -> dict:
    return {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [
            {
                "id": "run",
                "command": command,
                "args": args,
                "cwd": ".",
                "depends_on": [],
                "produces": produces or [],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": " ".join([command, *args]),
            }
        ],
    }


def test_run_workflow_step_completes_and_records_logs_and_state_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        state_path = root / "workflow_state.json"
        code = (
            "import json, pathlib, sys; "
            "state=json.loads(pathlib.Path(sys.argv[1]).read_text()); "
            "print(state['status']); "
            "print(state['steps'][0]['status'])"
        )
        dag = _dag(sys.executable, ["-c", code, str(state_path)], produces=["result_csv"])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag,
            state,
            "run",
            case_root=root,
            log_dir=root / "logs",
            state_path=state_path,
        )

        payload = result.state.to_json()
        assert payload["status"] == "completed"
        assert payload["current_step_id"] is None
        assert payload["completed_steps"] == ["run"]
        assert payload["failed_step_id"] is None
        assert payload["steps"][0]["status"] == "completed"
        assert payload["steps"][0]["attempt"] == 1
        assert payload["steps"][0]["exit_code"] == 0
        assert payload["steps"][0]["produced_artifacts"] == ["result_csv"]
        assert Path(result.stdout_log).read_text().splitlines() == ["running", "running"]
        assert Path(result.stderr_log).read_text() == ""
        assert json.loads(state_path.read_text()) == payload


def test_run_workflow_step_marks_nonzero_exit_failed() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        code = "import sys; print('failure text', file=sys.stderr); sys.exit(7)"
        dag = _dag(sys.executable, ["-c", code])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag,
            state,
            "run",
            case_root=root,
            log_dir=root / "logs",
        )

        payload = result.state.to_json()
        assert payload["status"] == "failed"
        assert payload["current_step_id"] == "run"
        assert payload["failed_step_id"] == "run"
        assert payload["completed_steps"] == []
        assert payload["steps"][0]["status"] == "failed"
        assert payload["steps"][0]["exit_code"] == 7
        assert Path(result.stderr_log).read_text().strip() == "failure text"


def test_run_workflow_step_allows_missing_optional_artifacts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        dag = _dag(sys.executable, ["-c", "print('ok')"], produces=["optional_vm"])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag,
            state,
            "run",
            case_root=root,
            log_dir=root / "logs",
            expected_artifacts=(
                DataArtifact(
                    artifact_id="optional_vm",
                    path_pattern="{time}/Vm",
                    format="openfoam_time_dirs",
                    optional=True,
                ),
            ),
            driver_context=driver_context(_ParallelOutputPlugin(), source="test:parallel-output"),
        )

        payload = result.state.to_json()
        assert payload["status"] == "completed"
        assert payload["steps"][0]["status"] == "completed"


def test_run_workflow_step_accepts_decomposed_time_artifact() -> None:
    # A parallel, not-yet-reconstructed run writes processor0/<time>/<field>.
    # The required time_indexed artifact must be considered produced.
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = (
            "import pathlib; "
            "d=pathlib.Path('processor0/0.001'); d.mkdir(parents=True); "
            "(d/'Vm').write_text('x')"
        )
        dag = _dag(sys.executable, ["-c", script], produces=["vm_field"])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag, state, "run",
            case_root=root, log_dir=root / "logs",
            expected_artifacts=(
                DataArtifact(
                    artifact_id="vm_field",
                    path_pattern="{time}/Vm",
                    format="openfoam_time_dirs",
                    time_indexed=True,
                ),
            ),
            driver_context=driver_context(_ParallelOutputPlugin(), source="test:parallel-output"),
        )

        payload = result.state.to_json()
        assert payload["status"] == "completed"
        assert payload["steps"][0]["status"] == "completed"
        assert payload["steps"][0]["produced_artifacts"] == ["vm_field"]


def test_run_workflow_step_accepts_reconstructed_time_artifact() -> None:
    # Serial / reconstructed location <time>/<field> still satisfies the gate.
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = (
            "import pathlib; "
            "d=pathlib.Path('0.001'); d.mkdir(parents=True); "
            "(d/'Vm').write_text('x')"
        )
        dag = _dag(sys.executable, ["-c", script], produces=["vm_field"])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag, state, "run",
            case_root=root, log_dir=root / "logs",
            expected_artifacts=(
                DataArtifact(
                    artifact_id="vm_field",
                    path_pattern="{time}/Vm",
                    format="openfoam_time_dirs",
                    time_indexed=True,
                ),
            ),
        )
        assert result.state.to_json()["status"] == "completed"


def test_run_workflow_step_missing_time_artifact_still_fails() -> None:
    # Neither reconstructed nor decomposed location exists -> missing_artifacts.
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        dag = _dag(sys.executable, ["-c", "print('ok')"], produces=["vm_field"])
        state = initial_workflow_state(dag)
        assert state is not None

        result = run_workflow_step(
            dag, state, "run",
            case_root=root, log_dir=root / "logs",
            expected_artifacts=(
                DataArtifact(
                    artifact_id="vm_field",
                    path_pattern="{time}/Vm",
                    format="openfoam_time_dirs",
                    time_indexed=True,
                ),
            ),
        )
        payload = result.state.to_json()
        assert payload["status"] == "failed"
        codes = {d["code"] for d in payload["steps"][0]["diagnostics"]}
        assert "missing_artifacts" in codes


def test_run_workflow_step_rejects_incomplete_dependencies() -> None:
    dag = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [
            {
                "id": "mesh",
                "command": sys.executable,
                "args": ["-c", "pass"],
                "cwd": ".",
                "depends_on": [],
                "produces": [],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": sys.executable,
            },
            {
                "id": "solve",
                "command": sys.executable,
                "args": ["-c", "pass"],
                "cwd": ".",
                "depends_on": ["mesh"],
                "produces": [],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": sys.executable,
            },
        ],
    }
    state = initial_workflow_state(dag)
    assert state is not None

    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(ValueError, match="incomplete dependencies"):
            run_workflow_step(
                dag, state, "solve", case_root=Path(temp_dir),
                log_dir=Path(temp_dir) / "logs",
            )


def test_run_workflow_step_rejects_cwd_escape() -> None:
    dag = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [
            {
                "id": "run",
                "command": sys.executable,
                "args": ["-c", "pass"],
                "cwd": "..",
                "depends_on": [],
                "produces": [],
                "consumes": [],
                "retry_policy": {"max_attempts": 1},
                "command_display": sys.executable,
            },
        ],
    }
    state = initial_workflow_state(dag)
    assert state is not None

    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(ValueError, match="escapes case root"):
            run_workflow_step(
                dag, state, "run", case_root=Path(temp_dir),
                log_dir=Path(temp_dir) / "logs",
            )


def test_case_script_step_preserves_dyld_vars_through_shell_hop() -> None:
    # The shell wrapper preserves dynamic-library variables for case scripts.
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        script = root / "run-case"
        script.write_text("#!/bin/sh\necho \"$DYLD_LIBRARY_PATH\"\n")
        script.chmod(0o755)

        dag = _dag("run-case", [])
        state = initial_workflow_state(dag)
        assert state is not None
        context = driver_context(
            MinimalTestPlugin(entrypoint="run-case"),
            source="test:workflow-runner",
        )

        marker = "/marker/path/for/regression/test"
        result = run_workflow_step(
            dag,
            state,
            "run",
            case_root=root.resolve(),
            log_dir=root / "logs",
            env={"PATH": __import__("os").environ.get("PATH", ""), "DYLD_LIBRARY_PATH": marker},
            driver_context=context,
        )

        assert result.state.to_json()["steps"][0]["exit_code"] == 0
        assert Path(result.stdout_log).read_text().strip() == marker


def test_case_script_invocation_embeds_dyld_vars_literally_in_argv() -> None:
    # Mechanism-level check independent of macOS SIP actually being active:
    # for a CASE_SCRIPT_COMMANDS-family step, the argv passed to the child
    # process must carry DYLD_* values as literal text (surviving even
    # if the OS strips them from the *inherited* environment of the shell
    # that's about to exec them), not rely solely on `env=`.
    # Process ownership now uses Popen, so retain this as the pure argv
    # boundary rather than replacing Popen with a test double.
    from omnidriver.core.runtime.workflow_runner import _argv_for_execution

    argv = _argv_for_execution(
        "run-case", "/case/run-case", (),
        {"PATH": __import__("os").environ.get("PATH", ""), "DYLD_LIBRARY_PATH": "/marker/xyz"},
        driver_context(
            MinimalTestPlugin(entrypoint="run-case"),
            source="test:workflow-runner",
        ),
    )
    assert any("/marker/xyz" in str(part) for part in argv), argv
