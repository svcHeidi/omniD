"""Manifest validation uses file evidence and the explicitly selected executable."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.runtime_profile import configure_runtime_environment


@pytest.fixture
def complete_manifest(tmp_path: Path):
    names = ("cardiacFoam", "libelectroModels", "libionicModels", "libgenericWriter",
             "libactiveTensionModels", "libphysicsModel")
    artifacts = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(f"fake-{name}".encode())
        if name == "cardiacFoam":
            path.chmod(0o755)
        artifacts.append({"name": name, "path": str(path),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    payload = {
        "schema_version": 1,
        "plugin": "org.cardiacfoam",
        "backend": "lightweight",
        "openfoam": {"root": str(tmp_path)},
        "solids4foam": {"root": None},
        "linked_libraries": ["libphysicsModel.dylib"],
        "artifacts": artifacts,
    }
    manifest = tmp_path / "build.json"
    env = {
        "DRIVERFOAM_CARDIACFOAM_BACKEND": "lightweight",
        "DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST": str(manifest),
        "WM_PROJECT_DIR": str(tmp_path),
        "PATH": str(tmp_path),
    }
    return payload, manifest, env


def _configure(fixture):
    payload, manifest, env = fixture
    manifest.write_text(json.dumps(payload))
    return configure_runtime_environment(env)


def test_valid_complete_manifest(complete_manifest):
    env, error = _configure(complete_manifest)
    assert error is None
    assert env["DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST"] == str(complete_manifest[1])


@pytest.mark.parametrize("omitted", [False, True])
def test_artifacts_must_be_present_and_nonempty(complete_manifest, omitted):
    payload, _, _ = complete_manifest
    if omitted:
        del payload["artifacts"]
    else:
        payload["artifacts"] = []
    _, error = _configure(complete_manifest)
    assert "non-empty artifacts list" in error


def test_duplicate_artifact_names(complete_manifest):
    payload, _, _ = complete_manifest
    payload["artifacts"].append(dict(payload["artifacts"][0]))
    _, error = _configure(complete_manifest)
    assert "duplicate artifact 'cardiacFoam'" in error


@pytest.mark.parametrize("name", ["cardiacFoam", "libelectroModels", "libphysicsModel"])
def test_missing_required_artifact(complete_manifest, name):
    payload, _, _ = complete_manifest
    payload["artifacts"] = [item for item in payload["artifacts"] if item["name"] != name]
    _, error = _configure(complete_manifest)
    assert f"missing required artifact {name}" in error


@pytest.mark.parametrize("value", [None, 0, 2, True, "1"])
def test_wrong_schema(complete_manifest, value):
    complete_manifest[0]["schema_version"] = value
    _, error = _configure(complete_manifest)
    assert "schema_version" in error


@pytest.mark.parametrize("value", [None, "other.plugin"])
def test_wrong_plugin(complete_manifest, value):
    complete_manifest[0]["plugin"] = value
    _, error = _configure(complete_manifest)
    assert "plugin does not match" in error


@pytest.mark.parametrize("value", [None, "", "/wrong/openfoam"])
def test_wrong_openfoam_root(complete_manifest, value):
    complete_manifest[0]["openfoam"]["root"] = value
    _, error = _configure(complete_manifest)
    assert "openfoam root is missing or does not match" in error


def test_solver_must_match_selected_path(complete_manifest, tmp_path):
    other = tmp_path / "other/cardiacFoam"
    other.parent.mkdir()
    other.write_bytes(b"different-solver")
    other.chmod(0o755)
    complete_manifest[2]["PATH"] = str(other.parent)
    _, error = _configure(complete_manifest)
    assert "solver does not match configured PATH executable" in error


def test_changed_library_digest(complete_manifest):
    artifact = complete_manifest[0]["artifacts"][1]
    Path(artifact["path"]).write_bytes(b"changed-library")
    _, error = _configure(complete_manifest)
    assert "Build artifact changed since manifest creation" in error
    assert artifact["path"] in error


@pytest.mark.parametrize("field,value,expected", [
    ("path", "relative/library.so", "requires an absolute path"),
    ("sha256", "", "artifact is unavailable"),
    ("sha256", "not-a-digest", "changed since manifest creation"),
])
def test_artifact_evidence_is_required(complete_manifest, field, value, expected):
    complete_manifest[0]["artifacts"][1][field] = value
    _, error = _configure(complete_manifest)
    assert expected in error


def test_missing_explicit_path_does_not_use_ambient_path(complete_manifest, monkeypatch):
    _, _, env = complete_manifest
    monkeypatch.setenv("PATH", env.pop("PATH"))
    _, error = _configure(complete_manifest)
    assert error == "cardiacFoam is unavailable on the configured PATH"


def test_wrong_solids4foam_root(complete_manifest, tmp_path):
    payload, _, env = complete_manifest
    solids = tmp_path / "solids4foam"
    for relative in ("src/solids4FoamModels/physicsModel/physicsModel.H",
                     "src/solids4FoamModels/lnInclude/physicsModel.H"):
        header = solids / relative
        header.parent.mkdir(parents=True, exist_ok=True)
        header.write_text("// fake header\n")
    payload["backend"] = "full"
    payload["solids4foam"]["root"] = str(tmp_path / "different-solids")
    payload["linked_libraries"] = ["libsolids4FoamModels.so", "libelectroMechanicalModels.so"]
    payload["artifacts"] = [a for a in payload["artifacts"] if a["name"] != "libphysicsModel"]
    for name in ("libsolids4FoamModels", "libelectroMechanicalModels"):
        library = tmp_path / f"{name}.so"
        library.write_bytes(name.encode())
        payload["artifacts"].append({"name": name, "path": str(library),
                                     "sha256": hashlib.sha256(library.read_bytes()).hexdigest()})
    env["DRIVERFOAM_CARDIACFOAM_BACKEND"] = "full"
    env["DRIVERFOAM_CARDIACFOAM_SOLIDS4FOAM_ROOT"] = str(solids)
    _, error = _configure(complete_manifest)
    assert "solids4foam root is missing or does not match" in error
