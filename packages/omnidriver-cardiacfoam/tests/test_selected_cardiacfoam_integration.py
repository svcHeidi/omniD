"""T7's opt-in driver/checker harness has no tutorial-marker dependency."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from selected_cardiacfoam_fixture import (
    BACKEND_ENV,
    BUILD_MANIFEST_ENV,
    CASE_MANIFEST_ENV,
    OPENFOAM_BASHRC_ENV,
    OUTPUT_ROOT_ENV,
    REGRESSION_SCOPE_ENV,
    SOURCE_REVISION_ENV,
    SOURCE_ROOT_ENV,
    selected_runtime_from_environment,
    selected_source_from_environment,
)
from selected_cardiacfoam_integration import (
    _run_command,
    load_integration_commands,
    run_selected_integration,
)


def _git(root: Path, *args: str) -> str:
    import subprocess

    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _runtime(tmp_path: Path):
    source_root = tmp_path / "source"
    path = source_root / "src" / "model.C"
    path.parent.mkdir(parents=True)
    path.write_text("// source\n")
    input_path = source_root / "tutorials" / "unmarked" / "system" / "controlDict"
    input_path.parent.mkdir(parents=True)
    content = b"endTime 1;\n"
    input_path.write_bytes(content)
    _git(tmp_path, "init", str(source_root))
    _git(source_root, "config", "user.email", "fixture@example.invalid")
    _git(source_root, "config", "user.name", "Fixture")
    _git(source_root, "add", ".")
    _git(source_root, "commit", "-m", "fixture")
    revision = _git(source_root, "rev-parse", "HEAD").strip()
    source = selected_source_from_environment({
        SOURCE_ROOT_ENV: str(source_root),
        SOURCE_REVISION_ENV: revision,
    })

    foam_root = tmp_path / "foam"
    appbin = foam_root / "appbin"
    libbin = foam_root / "libbin"
    appbin.mkdir(parents=True)
    libbin.mkdir()
    solver = appbin / "cardiacFoam"
    solver.write_text("#!/bin/sh\nexit 0\n")
    solver.chmod(0o755)
    artifacts = [("cardiacFoam", solver)]
    for name in ("electroModels", "ionicModels", "genericWriter", "activeTensionModels", "physicsModel"):
        library = libbin / f"lib{name}.dylib"
        library.write_bytes(name.encode())
        artifacts.append((f"lib{name}", library))
    bashrc = foam_root / "etc" / "bashrc"
    bashrc.parent.mkdir()
    bashrc.write_text(
        f"export WM_PROJECT_DIR={foam_root}\n"
        "export WM_PROJECT_VERSION=v2412\n"
        "export WM_OPTIONS=test\n"
        f"export PATH={appbin}:$PATH\n"
        f"export FOAM_USER_LIBBIN={libbin}\n"
    )
    build_manifest = tmp_path / "build.json"
    build_manifest.write_text(json.dumps({
        "schema_version": 1, "plugin": "org.cardiacfoam", "backend": "lightweight",
        "openfoam": {"root": str(foam_root)}, "solids4foam": {"root": None},
        "linked_libraries": ["libphysicsModel.dylib"],
        "artifacts": [
            {"name": name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in artifacts
        ],
    }))
    case_manifest = tmp_path / "case.json"
    case_manifest.write_text(json.dumps({
        "schema_version": 1,
        "case_id": "unmarked-case",
        "inputs": [{
            "source": "tutorials/unmarked/system/controlDict",
            "destination": "case/system/controlDict",
            "sha256": hashlib.sha256(content).hexdigest(),
        }],
        "integration": {
            "driver_command": ["{python}", "-c", "from pathlib import Path; Path('driver.ok').write_text('ok')"],
            "solver_checker_command": ["{python}", "-c", "from pathlib import Path; assert Path('driver.ok').read_text() == 'ok'"],
            "timeout_s": 30,
        },
    }))
    output_root = tmp_path / "output"
    output_root.mkdir()
    return selected_runtime_from_environment(
        source,
        repository_root=tmp_path / "omnidriver",
        environment={
            OPENFOAM_BASHRC_ENV: str(bashrc),
            BACKEND_ENV: "lightweight",
            BUILD_MANIFEST_ENV: str(build_manifest),
            OUTPUT_ROOT_ENV: str(output_root),
            CASE_MANIFEST_ENV: str(case_manifest),
            REGRESSION_SCOPE_ENV: "fixture",
        },
    )


def test_driver_and_solver_checker_evidence_are_recorded_separately(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    evidence = run_selected_integration(runtime, load_integration_commands(runtime))

    assert evidence.driver.returncode == 0
    assert evidence.solver_checker.returncode == 0
    assert evidence.driver.log_path != evidence.solver_checker.log_path
    assert evidence.case_root == evidence.stage_root / "case"
    payload = json.loads(evidence.evidence_path.read_text())
    assert payload["case_root"] == str(evidence.case_root)
    assert payload["driver"]["returncode"] == 0
    assert payload["solver_checker"]["returncode"] == 0
    assert (evidence.stage_root / "case/system/controlDict").is_file()


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_timeout_kills_harness_owned_descendant_and_records_evidence(tmp_path: Path) -> None:
    """The outer native-test timeout owns the complete command process group."""
    pid_file = tmp_path / "child.pid"
    child_code = (
        "import pathlib, time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(__import__('os').getpid().__str__()); "
        "time.sleep(30)"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(30)"
    )

    evidence = _run_command(
        (sys.executable, "-c", parent_code),
        cwd=tmp_path,
        log_name="timeout.log",
        timeout_s=1,
    )

    assert evidence.timed_out
    assert evidence.termination_error is None
    assert Path(evidence.log_path).is_file()
    assert pid_file.exists(), "fixture child did not start"
    child_pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    try:
        while time.monotonic() < deadline and _pid_exists(child_pid):
            time.sleep(0.02)
        assert not _pid_exists(child_pid), "timeout left a harness descendant running"
    finally:
        if _pid_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_timeout_writes_evidence_when_cleanup_helper_raises(tmp_path: Path) -> None:
    """A cleanup failure must not hide the original timeout from the record."""
    with mock.patch(
        "selected_cardiacfoam_integration._terminate_process_group",
        side_effect=subprocess.TimeoutExpired([sys.executable], 1),
    ):
        evidence = _run_command(
            (sys.executable, "-c", "import time; time.sleep(30)"),
            cwd=tmp_path,
            log_name="cleanup-failure.log",
            timeout_s=1,
        )

    assert evidence.timed_out
    assert evidence.termination_error is not None
    assert "process-group cleanup failed" in evidence.termination_error
    assert Path(evidence.log_path).is_file()
