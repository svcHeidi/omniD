"""The environment and machine connections (2026-09-28, roadmap item 5)."""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.cli import main
from omnidriver.core.environment_connection import environment_report, render_prefix, stack_connection
from omnidriver.core.plugin_profile import EnvironmentConnection, SuppliedVariable, load_plugin_profile
from omnidriver.core.runtime.host_facts import host_facts

_TOY = "plugins.toy:ToyStack"


def _connection() -> EnvironmentConnection:
    return EnvironmentConnection(
        supplied=(
            SuppliedVariable("TOY_RC", True, "the file to source"),
            SuppliedVariable("DYLD_LIBRARY_PATH", False, "exported after the source"),
            SuppliedVariable("TOY_MPI_BIN", False, "first on PATH"),
            SuppliedVariable("TOY_UNSET", False, "not set, so not exported"),
        ),
        source="TOY_RC", path_prepend=("TOY_MPI_BIN",), mpi_launcher="mpirun",
    )


def test_the_prefix_sources_first_then_exports_then_path():
    prefix = render_prefix(_connection(), {
        "TOY_RC": "/opt/toy rc", "DYLD_LIBRARY_PATH": "/opt/lib", "TOY_MPI_BIN": "/opt/mpi/bin",
    })
    assert prefix == (
        "source '/opt/toy rc'; export DYLD_LIBRARY_PATH=/opt/lib; "
        'export PATH=/opt/mpi/bin:"$PATH"; '
    )
    assert render_prefix(_connection(), {}) == ""


def test_a_manifest_names_only_supplied_variables(tmp_path):
    profile = tmp_path / "plugin.yaml"
    body = (
        "schema_version: 1\nplugin: {id: toy, api_version: '3'}\nenvironment:\n"
        "  supplied:\n    - {name: TOY_RC, required: true, why: sourced}\n"
    )
    profile.write_text(body + "  source: TOY_RC\n  mpi_launcher: mpirun\n")
    connection = load_plugin_profile(profile).environment
    assert (connection.source, connection.mpi_launcher) == ("TOY_RC", "mpirun")
    profile.write_text(body + "  source: NOT_DECLARED\n")
    with pytest.raises(ValueError, match="NOT_DECLARED"):
        load_plugin_profile(profile)
    profile.write_text(body + "  searched_paths: [/opt]\n")
    with pytest.raises(ValueError, match="unknown keys"):
        load_plugin_profile(profile)


class _Provider:
    def __init__(self, connection, cxx_mapping=None):
        self._profile = SimpleNamespace(environment=connection, cxx_mapping=cxx_mapping, plugin_id="toy")

    def get_profile(self):
        return self._profile


def _context(connection):
    preflight_calls = []

    def diagnostics(dag, *, env, driver_context):
        preflight_calls.append((dag, env))
        return ()

    answers = {
        "get_solver_commands": lambda: frozenset({"toySolver"}),
        "get_auxiliary_commands": lambda: frozenset(),
        "get_environment_commands": lambda: frozenset(),
        "get_environment_diagnostics": diagnostics,
    }
    stack = SimpleNamespace(call=lambda member, *args, **kwargs: answers[member](*args, **kwargs))
    return SimpleNamespace(
        providers=(_Provider(connection),), stack=stack,
        identity=SimpleNamespace(to_json=lambda: {"providers": [{"id": "toy"}]}),
    ), preflight_calls


def test_an_unset_required_variable_is_refused_by_name_and_nothing_runs():
    context, calls = _context(_connection())
    report = environment_report(context, {"PATH": os.environ["PATH"]})
    assert report["status"] == "failed"
    assert [d["code"] for d in report["preflight"]] == ["environment_variable_not_supplied"]
    assert report["shell_prefix"] is None and calls == []


def test_the_preflight_runs_on_the_environment_the_prefix_produces(tmp_path):
    rc = tmp_path / "rc.sh"
    rc.write_text("export TOY_SOURCED=yes\n")
    (tmp_path / "bin").mkdir()
    context, calls = _context(_connection())
    report = environment_report(context, {
        "PATH": os.environ["PATH"], "TOY_RC": str(rc), "TOY_MPI_BIN": str(tmp_path / "bin"),
    })
    assert report["status"] == "ok", report
    (dag, env), = calls
    assert env["TOY_SOURCED"] == "yes"
    assert env["PATH"].split(":")[0] == str(tmp_path / "bin")
    assert [step["command"] for step in dag["steps"]] == ["toySolver", "mpirun"]
    assert dag["steps"][1]["args"] == ["-np", "2", "toySolver"]


def test_two_providers_may_not_both_name_a_file_to_source():
    context, _ = _context(_connection())
    other = EnvironmentConnection(supplied=(SuppliedVariable("OTHER_RC", True, "x"),), source="OTHER_RC")
    context.providers = (_Provider(_connection()), _Provider(other))
    with pytest.raises(ValueError, match="one environment to source"):
        stack_connection(context)


def test_env_takes_only_a_plugin():
    with pytest.raises(SystemExit):
        main(["env", "--plugin", _TOY, "--entry", "toyTutorial"])


def test_a_launcher_step_records_the_launcher_and_its_ranks(tmp_path):
    launcher = tmp_path / "mpirun"
    launcher.write_text("#!/bin/sh\necho 'mpirun (Toy MPI) 1.0'\n")
    launcher.chmod(0o755)
    facts = host_facts(
        "mpirun", ["-np", "4", "toySolver"],
        {"PATH": str(tmp_path), "SLURM_NTASKS": "4", "OMP_NUM_THREADS": "1", "TOY_RC": "/rc", "HOME": "/h"},
        declared_variables=("TOY_RC", "TOY_UNSET"),
    )
    assert facts["hostname"] == socket.gethostname()
    assert facts["cpu_count"] == os.cpu_count()
    assert facts["ambient"] == {"OMP_NUM_THREADS": "1", "SLURM_NTASKS": "4"}
    assert facts["declared"] == {"TOY_RC": "/rc"}
    assert facts["launcher"]["ranks"] == 4
    assert facts["launcher"]["version"] == ["mpirun (Toy MPI) 1.0"]
    assert "launcher" not in host_facts("toySolver", [], {"PATH": ""})


def test_every_step_attempt_records_its_host(tmp_path, capsys):
    native = tmp_path / "native" / "toyTutorial" / "constant"
    native.mkdir(parents=True)
    (native / "mesh.json").write_text(json.dumps({"cells": "1"}))
    exit_code = main([
        "run", "--strict", "--plugin", _TOY, "--entry", "toyTutorial",
        "--cases-root", str(tmp_path / "native"), "--scratch-dir", str(tmp_path / "scratch"),
    ])
    assert exit_code == 0, capsys.readouterr().out
    (state_path,) = Path(tmp_path / "scratch").rglob("workflow_state.json")
    (step,) = json.loads(state_path.read_text())["steps"]
    assert step["status"] == "completed"
    assert step["host"]["hostname"] == socket.gethostname()
    assert "launcher" not in step["host"]


def test_a_supplied_source_root_that_is_not_a_directory_is_refused(tmp_path):
    from omnidriver.core.plugin_profile import CxxMapping

    context, calls = _context(_connection())
    context.providers = (_Provider(None, CxxMapping("TOY_TREE", "src", tmp_path / "a.json")),)
    report = environment_report(context, {"PATH": os.environ["PATH"], "TOY_TREE": str(tmp_path / "absent")})
    assert [d["code"] for d in report["preflight"]] == ["plugin_cxx_source_unavailable"]
    assert report["status"] == "failed" and calls == []
    assert report["variables"][0]["name"] == "TOY_TREE"
