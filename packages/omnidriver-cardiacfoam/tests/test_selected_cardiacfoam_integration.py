"""T7's opt-in driver/checker harness has no tutorial-marker dependency."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

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
