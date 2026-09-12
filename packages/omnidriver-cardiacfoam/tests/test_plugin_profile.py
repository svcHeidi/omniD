from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from omnidriver.cardiacfoam import runtime_profile
from omnidriver.cardiacfoam.runtime_profile import configure_runtime_environment
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from conftest import skip_without_monorepo


def test_cardiac_profile_declares_case_files_and_cxx_provenance() -> None:
    profile = CardiacFoamPlugin().get_profile()

    assert profile.plugin_id == "org.cardiacfoam"
    assert {rule.path for rule in profile.case_files} >= {
        "system/controlDict",
        "constant/physicsProperties",
        "constant/electroProperties",
    }
    assert profile.cxx_mapping is not None
    assert profile.cxx_mapping.allowlist_path.is_file()
    assert profile.digest.startswith("sha256:")


@skip_without_monorepo
def test_cardiac_profile_cxx_source_roots_exist() -> None:
    """cxx_mapping.source_roots points into the C++ solver source tree,
    which this standalone Python-only repo doesn't ship (see
    GITHUB_MIGRATION.md: "we are moving *only the Python framework*").
    Only verifiable when checked out inside the full cardiacFoam monorepo."""

    profile = CardiacFoamPlugin().get_profile()
    assert all(path.is_dir() for path in profile.cxx_mapping.source_roots)


def test_cardiac_catalog_partitions_entries_by_document() -> None:
    catalog = CardiacFoamPlugin().get_dictionary_catalog()

    assert {"electroProperties", "physicsProperties", "controlDict"} <= set(catalog.documents)
    assert {entry.driver_path for entry in catalog.entries_for("physicsProperties")} == {"type"}
    assert {entry.driver_path for entry in catalog.entries_for("controlDict")} >= {"deltaT", "endTime"}


def test_cardiac_runtime_requires_a_discoverable_solver(tmp_path: Path) -> None:
    del tmp_path
    env, error = CardiacFoamPlugin().configure_execution_environment({})

    assert env == {}
    assert error is not None
    assert "cardiacFoam is unavailable" in error


def test_cardiac_runtime_exports_one_validated_solids4foam_root(tmp_path: Path) -> None:
    root = tmp_path / "solids4foam"
    header = root / "src/solids4FoamModels/solidModels/solidModel/solidModel.H"
    ln_include = root / "src/solids4FoamModels/lnInclude/solidModel.H"
    header.parent.mkdir(parents=True)
    ln_include.parent.mkdir(parents=True)
    header.write_text("// source header\n")
    ln_include.write_text("// generated include\n")
    manifest = tmp_path / "cardiacFoam.build.json"
    solver = _write_complete_full_manifest(manifest, tmp_path, root)

    env, error = CardiacFoamPlugin().configure_execution_environment({
        "DRIVERFOAM_CARDIACFOAM_BACKEND": "full",
        "DRIVERFOAM_CARDIACFOAM_SOLIDS4FOAM_ROOT": str(root),
        "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST": str(manifest),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(solver.parent),
    })

    assert error is None
    assert env["SOLIDS4FOAM_INST_DIR"] == str(root.resolve())
    assert env["DRIVERFOAM_CARDIACFOAM_SOLIDS4FOAM_ROOT"] == str(root.resolve())


def test_infer_backend_from_linked_libraries() -> None:
    options = {
        "lightweight": {
            "required_libraries": ["libphysicsModel"],
            "forbidden_libraries": ["libsolids4FoamModels", "libelectroMechanicalModels"],
        },
        "full": {
            "required_libraries": ["libsolids4FoamModels", "libelectroMechanicalModels"],
            "forbidden_libraries": ["libphysicsModel"],
        },
    }
    lightweight_linked = ("libphysicsModel.dylib", "libelectroModels.dylib")
    full_linked = ("libsolids4FoamModels.dylib", "libelectroMechanicalModels.dylib")

    assert runtime_profile._infer_backend(lightweight_linked, options) == "lightweight"
    assert runtime_profile._infer_backend(full_linked, options) == "full"
    assert runtime_profile._infer_backend(lightweight_linked + full_linked, options) is None
    assert runtime_profile._infer_backend((), options) is None


def test_full_runtime_does_not_require_solids4foam_source_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "cardiacFoam.build.json"
    solver = _write_complete_full_manifest(manifest, tmp_path, None)
    monkeypatch.setattr(
        runtime_profile,
        "_linked_library_names",
        lambda _solver: ("libsolids4FoamModels.dylib", "libelectroMechanicalModels.dylib"),
    )

    env, error = configure_runtime_environment({
        "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST": str(manifest),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(solver.parent),
    })

    assert error is None
    assert env["DRIVERFOAM_CARDIACFOAM_BACKEND"] == "full"
    assert "SOLIDS4FOAM_INST_DIR" not in env


def _write_fake_library(directory: Path, bare_name: str, content: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"lib{bare_name}.dylib"
    path.write_bytes(content)
    return path


def _write_fake_lightweight_build(appbin: Path, libbin: Path, *, solver_content: bytes) -> Path:
    appbin.mkdir(parents=True, exist_ok=True)
    solver = appbin / "cardiacFoam"
    solver.write_bytes(solver_content)
    solver.chmod(0o755)
    for bare_name in ("electroModels", "ionicModels", "genericWriter", "activeTensionModels", "physicsModel"):
        _write_fake_library(libbin, bare_name, f"fake-{bare_name}".encode())
    return solver


def _write_complete_full_manifest(
    manifest: Path, foam_root: Path, solids_root: Path | None,
) -> Path:
    solver = foam_root / "appbin/cardiacFoam"
    solver.parent.mkdir(parents=True)
    solver.write_bytes(b"fake-solver")
    solver.chmod(0o755)
    names = ("electroModels", "ionicModels", "genericWriter", "activeTensionModels",
             "solids4FoamModels", "electroMechanicalModels")
    paths = [("cardiacFoam", solver)] + [
        (f"lib{name}", _write_fake_library(foam_root / "libbin", name, name.encode()))
        for name in names
    ]
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "plugin": "org.cardiacfoam",
        "backend": "full",
        "openfoam": {"root": str(foam_root)},
        "solids4foam": {"root": str(solids_root) if solids_root else None},
        "linked_libraries": ["libsolids4FoamModels.dylib", "libelectroMechanicalModels.dylib"],
        "artifacts": [
            {"name": name, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in paths
        ],
    }))
    return solver


def test_build_manifest_self_generates_from_compiled_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appbin = tmp_path / "appbin"
    libbin = tmp_path / "libbin"
    solver = _write_fake_lightweight_build(appbin, libbin, solver_content=b"fake-solver")
    monkeypatch.setattr(runtime_profile, "_linked_library_names", lambda binary: ("libphysicsModel.dylib",))

    manifest = tmp_path / "cardiacFoam.build.json"
    assert not manifest.exists()

    env, error = configure_runtime_environment({
        "DRIVERFOAM_CARDIACFOAM_BACKEND": "lightweight",
        "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST": str(manifest),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(solver.parent),
        "FOAM_USER_APPBIN": str(appbin),
        "FOAM_USER_LIBBIN": str(libbin),
    })

    assert error is None, error
    payload = json.loads(manifest.read_text())
    assert payload["backend"] == "lightweight"
    assert {artifact["name"] for artifact in payload["artifacts"]} == {
        "cardiacFoam",
        "libelectroModels",
        "libionicModels",
        "libgenericWriter",
        "libactiveTensionModels",
        "libphysicsModel",
    }
    solver_artifact = next(a for a in payload["artifacts"] if a["name"] == "cardiacFoam")
    assert solver_artifact["sha256"] == hashlib.sha256(b"fake-solver").hexdigest()


def test_build_manifest_self_heals_when_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appbin = tmp_path / "appbin"
    libbin = tmp_path / "libbin"
    solver = _write_fake_lightweight_build(appbin, libbin, solver_content=b"fake-solver-v2")

    manifest = tmp_path / "cardiacFoam.build.json"
    manifest.write_text(json.dumps({
        "backend": "lightweight",
        "openfoam": {"root": str(tmp_path)},
        "solids4foam": {"root": None},
        "linked_libraries": ["libphysicsModel.dylib"],
        "artifacts": [],
    }))
    stale_time = solver.stat().st_mtime - 10
    os.utime(manifest, (stale_time, stale_time))
    monkeypatch.setattr(runtime_profile, "_linked_library_names", lambda binary: ("libphysicsModel.dylib",))

    env, error = configure_runtime_environment({
        "DRIVERFOAM_CARDIACFOAM_BACKEND": "lightweight",
        "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST": str(manifest),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(solver.parent),
        "FOAM_USER_APPBIN": str(appbin),
        "FOAM_USER_LIBBIN": str(libbin),
    })

    assert error is None, error
    payload = json.loads(manifest.read_text())
    solver_artifact = next(a for a in payload["artifacts"] if a["name"] == "cardiacFoam")
    assert solver_artifact["sha256"] == hashlib.sha256(b"fake-solver-v2").hexdigest()


def test_cardiac_runtime_file_selects_backend_and_bashrc(tmp_path: Path) -> None:
    root = tmp_path / "solids4foam"
    for relative in (
        "src/solids4FoamModels/solidModels/solidModel/solidModel.H",
        "src/solids4FoamModels/lnInclude/solidModel.H",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// header\n")
    manifest = tmp_path / "cardiacFoam.build.json"
    solver = _write_complete_full_manifest(manifest, tmp_path, root)
    config = tmp_path / "driverfoam-runtime.yaml"
    config.write_text(
        "openfoam:\n  bashrc: /tmp/openfoam/etc/bashrc\n"
        "plugins:\n  org.cardiacfoam:\n"
        f"    backend: full\n    solids4foam_root: {root}\n"
        f"    build_manifest: {manifest}\n"
    )

    env, error = CardiacFoamPlugin().configure_execution_environment({
        "DRIVERFOAM_RUNTIME_CONFIG": str(config),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(solver.parent),
    })

    assert error is None
    assert env["DRIVERFOAM_CARDIACFOAM_BACKEND"] == "full"
    assert env["SOLIDS4FOAM_INST_DIR"] == str(root.resolve())
    assert CardiacFoamPlugin().get_openfoam_bashrc({
        "DRIVERFOAM_RUNTIME_CONFIG": str(config),
    }) == "/tmp/openfoam/etc/bashrc"
