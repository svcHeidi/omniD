"""OpenFOAM command authorization belongs to the OpenFOAM adapter."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from omnidriver.core.runtime.workflow import validate_workflow_commands
from omnidriver.openfoam.environment import openfoam_environment_context


def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_openfoam_environment_authorizes_its_declared_commands() -> None:
    assert validate_workflow_commands(
        _dag("blockMesh"), driver_context=openfoam_environment_context(),
    ) == ()


def test_openfoam_allrun_family_is_authorized() -> None:
    context = openfoam_environment_context()
    for command in ("Allrun", "Allclean", "Allrun.pre", "./Allrun.post"):
        assert validate_workflow_commands(_dag(command), driver_context=context) == ()


def test_an_installed_openfoam_app_is_authorized(monkeypatch) -> None:
    """An executable under an OpenFOAM app root is adapter-owned authorization."""
    monkeypatch.setattr(
        "omnidriver.openfoam.environment.is_installed_openfoam_application",
        lambda command: command == "someInstalledApp",
    )
    errors = [
        diagnostic
        for diagnostic in validate_workflow_commands(
            _dag("someInstalledApp"), driver_context=openfoam_environment_context(),
        )
        if diagnostic.level == "error"
    ]
    assert errors == []


def test_only_apps_in_openfoam_app_bins_are_authorized() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        appbin = Path(temp_dir) / "bin"
        appbin.mkdir()
        executable = appbin / "testOpenFOAMApp"
        executable.write_text("#!/bin/sh\n")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        previous_path = os.environ.get("PATH", "")
        previous_appbin = os.environ.get("FOAM_APPBIN")
        os.environ["PATH"] = f"{appbin}{os.pathsep}{previous_path}"
        os.environ["FOAM_APPBIN"] = str(appbin)
        try:
            context = openfoam_environment_context()
            assert validate_workflow_commands(_dag("testOpenFOAMApp"), driver_context=context) == ()
            errors = [
                item for item in validate_workflow_commands(_dag("notAnOpenFOAMApp"), driver_context=context)
                if item.level == "error"
            ]
            assert errors
        finally:
            os.environ["PATH"] = previous_path
            if previous_appbin is None:
                os.environ.pop("FOAM_APPBIN", None)
            else:
                os.environ["FOAM_APPBIN"] = previous_appbin
