"""Unit tests for the opt-in selected-source/native-fixture boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from selected_cardiacfoam_fixture import (
    BACKEND_ENV,
    BUILD_MANIFEST_ENV,
    CASE_MANIFEST_ENV,
    FixtureInputError,
    OPENFOAM_BASHRC_ENV,
    OUTPUT_ROOT_ENV,
    REGRESSION_SCOPE_ENV,
    SOURCE_REVISION_ENV,
    SOURCE_ROOT_ENV,
    load_case_input_manifest,
    materialize_case_inputs,
    selected_runtime_from_environment,
    selected_source_from_environment,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _selected_checkout(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "selected-source"
    (root / "src").mkdir(parents=True)
    (root / "tutorials").mkdir()
    (root / "src" / "model.C").write_text("// selected source\n")
    (root / "tutorials" / "case.foam").write_text("// selected tutorial\n")
    unmarked = root / "tutorials" / "unmarkedCase" / "system" / "controlDict"
    unmarked.parent.mkdir(parents=True)
    unmarked.write_text("endTime 1;\n")
    _git(root.parent, "init", str(root))
    _git(root, "config", "user.email", "fixtures@example.invalid")
    _git(root, "config", "user.name", "Fixture test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "selected fixture")
    return root, _git(root, "rev-parse", "HEAD").strip()


def _source_environment(root: Path, revision: str) -> dict[str, str]:
    return {SOURCE_ROOT_ENV: str(root), SOURCE_REVISION_ENV: revision}


def _native_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    foam_root = tmp_path / "openfoam"
    appbin = foam_root / "appbin"
    libbin = foam_root / "libbin"
    appbin.mkdir(parents=True)
    libbin.mkdir()
    solver = appbin / "cardiacFoam"
    solver.write_text("#!/bin/sh\nexit 0\n")
    solver.chmod(0o755)
    artifacts = [("cardiacFoam", solver)]
    for name in (
        "electroModels",
        "ionicModels",
        "genericWriter",
        "activeTensionModels",
        "physicsModel",
    ):
        path = libbin / f"lib{name}.dylib"
        path.write_bytes(name.encode())
        artifacts.append((f"lib{name}", path))
    bashrc = foam_root / "etc" / "bashrc"
    bashrc.parent.mkdir()
    bashrc.write_text(
        f"export WM_PROJECT_DIR={foam_root}\n"
        "export WM_PROJECT_VERSION=v2412\n"
        "export WM_OPTIONS=darwinArm64ClangDPInt32Opt\n"
        f"export PATH={appbin}:$PATH\n"
        f"export FOAM_USER_LIBBIN={libbin}\n"
    )
    manifest = tmp_path / "cardiacFoam.build.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "plugin": "org.cardiacfoam",
        "backend": "lightweight",
        "openfoam": {"root": str(foam_root)},
        "solids4foam": {"root": None},
        "linked_libraries": ["libphysicsModel.dylib"],
        "artifacts": [
            {"name": name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in artifacts
        ],
    }))
    case_manifest = tmp_path / "case-manifest.json"
    case_manifest.write_text("{}\n")
    output_root = tmp_path / "native-output"
    output_root.mkdir()
    return bashrc, manifest, case_manifest, output_root


def test_source_fixture_is_unselected_without_explicit_inputs() -> None:
    assert selected_source_from_environment({}) is None


def test_partial_source_selection_is_an_error() -> None:
    with pytest.raises(FixtureInputError, match="must be set together"):
        selected_source_from_environment({SOURCE_ROOT_ENV: "/tmp"})


def test_selected_source_records_permitted_tutorial_drift(tmp_path: Path) -> None:
    root, revision = _selected_checkout(tmp_path)
    (root / "tutorials" / "candidate.foam").write_text("candidate\n")

    selected = selected_source_from_environment(_source_environment(root, revision))

    assert selected is not None
    assert selected.root == root.resolve()
    assert selected.revision == revision
    assert selected.src_status == ""
    assert "tutorials/candidate.foam" in selected.permitted_drift_status
    assert selected.permitted_drift_digest.startswith("sha256:")


def test_selected_source_rejects_src_drift_before_staging(tmp_path: Path) -> None:
    root, revision = _selected_checkout(tmp_path)
    (root / "src" / "model.C").write_text("// dirty source\n")

    with pytest.raises(FixtureInputError, match="src/ drift"):
        selected_source_from_environment(_source_environment(root, revision))


def test_native_fixture_requires_all_explicit_inputs(tmp_path: Path) -> None:
    root, revision = _selected_checkout(tmp_path)
    source = selected_source_from_environment(_source_environment(root, revision))

    with pytest.raises(FixtureInputError, match="missing"):
        selected_runtime_from_environment(
            source,
            repository_root=tmp_path / "omnidriver",
            environment={OPENFOAM_BASHRC_ENV: "/missing/etc/bashrc"},
        )


def test_native_fixture_rejects_an_output_inside_source(tmp_path: Path) -> None:
    root, revision = _selected_checkout(tmp_path)
    source = selected_source_from_environment(_source_environment(root, revision))
    bashrc, manifest, case_manifest, _ = _native_inputs(tmp_path)
    environment = {
        OPENFOAM_BASHRC_ENV: str(bashrc),
        BACKEND_ENV: "lightweight",
        BUILD_MANIFEST_ENV: str(manifest),
        OUTPUT_ROOT_ENV: str(root / "outputs"),
        CASE_MANIFEST_ENV: str(case_manifest),
        REGRESSION_SCOPE_ENV: "single-cell-smoke",
    }
    (root / "outputs").mkdir()

    with pytest.raises(FixtureInputError, match="outside the selected source"):
        selected_runtime_from_environment(
            source, repository_root=tmp_path / "omnidriver", environment=environment
        )


def test_native_fixture_accepts_only_prevalidated_explicit_locations(tmp_path: Path) -> None:
    root, revision = _selected_checkout(tmp_path)
    source = selected_source_from_environment(_source_environment(root, revision))
    bashrc, manifest, case_manifest, output_root = _native_inputs(tmp_path)
    environment = {
        OPENFOAM_BASHRC_ENV: str(bashrc),
        BACKEND_ENV: "lightweight",
        BUILD_MANIFEST_ENV: str(manifest),
        OUTPUT_ROOT_ENV: str(output_root),
        CASE_MANIFEST_ENV: str(case_manifest),
        REGRESSION_SCOPE_ENV: "single-cell-smoke",
    }

    selected = selected_runtime_from_environment(
        source, repository_root=tmp_path / "omnidriver", environment=environment
    )

    assert selected is not None
    assert selected.source == source
    assert selected.output_root == output_root.resolve()
    assert dict(selected.openfoam_identity)["WM_PROJECT_VERSION"] == "v2412"
    assert selected.build_manifest_digest.startswith("sha256:")
    assert selected.regression_scope == "single-cell-smoke"


def test_committed_manifest_stages_an_unmarked_case_without_source_mutation(
    tmp_path: Path,
) -> None:
    root, revision = _selected_checkout(tmp_path)
    committed = (root / "tutorials" / "unmarkedCase" / "system" / "controlDict").read_bytes()
    source = selected_source_from_environment(_source_environment(root, revision))
    # The selected worktree may evolve, but committed mode must read the
    # named revision rather than silently treating it as a new baseline.
    (root / "tutorials" / "unmarkedCase" / "system" / "controlDict").write_text(
        "endTime 99;\n"
    )
    bashrc, manifest, case_manifest, output_root = _native_inputs(tmp_path)
    case_manifest.write_text(json.dumps({
        "schema_version": 1,
        "case_id": "unmarked-single-cell",
        "inputs": [{
            "source": "tutorials/unmarkedCase/system/controlDict",
            "destination": "case/system/controlDict",
            "sha256": hashlib.sha256(committed).hexdigest(),
        }],
    }))
    runtime = selected_runtime_from_environment(
        source,
        repository_root=tmp_path / "omnidriver",
        environment={
            OPENFOAM_BASHRC_ENV: str(bashrc),
            BACKEND_ENV: "lightweight",
            BUILD_MANIFEST_ENV: str(manifest),
            OUTPUT_ROOT_ENV: str(output_root),
            CASE_MANIFEST_ENV: str(case_manifest),
            REGRESSION_SCOPE_ENV: "single-cell-smoke",
        },
    )

    staged = materialize_case_inputs(runtime, load_case_input_manifest(runtime))

    assert staged.root.parent == output_root
    assert staged.input_policy == "committed"
    assert staged.input_digest.startswith("sha256:")
    assert (staged.root / "case/system/controlDict").read_bytes() == committed
    assert (root / "tutorials" / "unmarkedCase" / "system" / "controlDict").read_text() == "endTime 99;\n"
