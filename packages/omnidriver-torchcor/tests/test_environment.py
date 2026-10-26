"""TorchCor's preflight, without TorchCor: a stand-in python3 in a stand-in venv bin."""
from __future__ import annotations

from pathlib import Path

from omnidriver.torchcor.environment import torchcor_environment_diagnostics
from torchcor_testing import context_of, repository_with_runner

DAG = {"steps": [{"id": "solve", "command": "run_case.py", "args": ["case.json"]}]}


def _bin(root: Path) -> Path:
    directory = root / "bin"
    directory.mkdir(parents=True)
    python = directory / "python3"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    return directory


def _errors(env, root):
    context = context_of(repository_with_runner(root))
    return [d for d in torchcor_environment_diagnostics(DAG, env, context) if d.level == "error"]


def test_torchcors_python_first_on_path_is_clean(tmp_path):
    venv = _bin(tmp_path / "venv")
    assert _errors({"TORCHCOR_BIN": str(venv), "PATH": f"{venv}:/usr/bin"}, tmp_path) == []


def test_without_a_supplied_venv_any_python3_on_path_is_taken(tmp_path):
    other = _bin(tmp_path / "other")
    assert _errors({"PATH": str(other)}, tmp_path) == []


def test_no_python3_on_path_names_the_python3_the_runner_needs(tmp_path):
    venv, empty = _bin(tmp_path / "venv"), tmp_path / "empty"
    empty.mkdir()
    (error,) = _errors({"TORCHCOR_BIN": str(venv), "PATH": str(empty)}, tmp_path)
    assert (error.code, error.field) == ("program_not_on_path", "python3")


def test_another_python3_first_on_path_is_refused(tmp_path):
    venv, other = _bin(tmp_path / "venv"), _bin(tmp_path / "other")
    (error,) = _errors({"TORCHCOR_BIN": str(venv), "PATH": f"{other}:{venv}"}, tmp_path)
    assert error.code == "torchcor_python_not_torchcors" and str(other) in error.message
