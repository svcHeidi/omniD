"""OpenFOAM command authorization belongs to the OpenFOAM adapter."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from omnidriver.core.runtime.workflow import validate_workflow_commands
from omnidriver.core.plugin_interface import load_plugin_context


def _dag(command: str) -> dict:
    return {"steps": [{"id": "s", "command": command, "depends_on": []}]}


def test_openfoam_environment_authorizes_its_declared_commands() -> None:
    assert validate_workflow_commands(
        _dag("blockMesh"), driver_context=load_plugin_context("openfoam-environment"),
    ) == ()


def test_openfoam_allrun_family_is_authorized() -> None:
    context = load_plugin_context("openfoam-environment")
    for command in ("Allrun", "Allclean", "Allrun.pre", "./Allrun.post"):
        assert validate_workflow_commands(_dag(command), driver_context=context) == ()


def test_an_installed_openfoam_app_is_authorized(monkeypatch) -> None:
    monkeypatch.setattr(
        "omnidriver.openfoam.environment.is_installed_openfoam_application",
        lambda command, env: command == "someInstalledApp",
    )
    errors = [
        diagnostic
        for diagnostic in validate_workflow_commands(
            _dag("someInstalledApp"), driver_context=load_plugin_context("openfoam-environment"), env={},
        )
        if diagnostic.level == "error"
    ]
    assert errors == []


def test_only_apps_in_the_execution_environments_app_bins_are_authorized(tmp_path) -> None:
    appbin = tmp_path / "bin"
    appbin.mkdir()
    executable = appbin / "testOpenFOAMApp"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    env = {"PATH": f"{appbin}{os.pathsep}{os.environ.get('PATH', '')}", "FOAM_APPBIN": str(appbin)}
    context = load_plugin_context("openfoam-environment")
    assert validate_workflow_commands(_dag("testOpenFOAMApp"), driver_context=context, env=env) == ()
    errors = [
        item for item in validate_workflow_commands(_dag("notAnOpenFOAMApp"), driver_context=context, env=env)
        if item.level == "error"
    ]
    assert errors


def test_an_app_is_looked_up_in_the_execution_environment_not_the_process_one(tmp_path, monkeypatch) -> None:
    appbin = tmp_path / "bin"
    appbin.mkdir()
    executable = appbin / "testOpenFOAMApp"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{appbin}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FOAM_APPBIN", str(appbin))
    context = load_plugin_context("openfoam-environment")
    for env in (None, {"PATH": os.defpath}):
        codes = {d.code for d in validate_workflow_commands(_dag("testOpenFOAMApp"), driver_context=context, env=env)}
        assert "unknown_workflow_command" in codes
