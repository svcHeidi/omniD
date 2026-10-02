"""A cardiacFOAM repository's ``omnidriver.toml`` supplies the C++ source the profile otherwise takes from a variable."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from omnidriver.cli import main

VARIABLE = "OMNIDRIVER_NATIVE_TUTORIALS"


@pytest.fixture(autouse=True)
def _restore_the_variable(monkeypatch):
    monkeypatch.setenv(VARIABLE, "placeholder")
    monkeypatch.delenv(VARIABLE)


def _repo(root: Path, *, source: str = "src") -> Path:
    for folder in ("tutorials", "src"):
        (root / folder).mkdir(parents=True)
    (root / "omnidriver.toml").write_text(
        f'plugin = "cardiacfoam"\ntutorials = "tutorials"\nsource = "{source}"\nscripts = "applications/scripts"\n'
    )
    return root


def _env(capsys, *argv):
    main(["env", *argv])
    return {item["name"]: item for item in json.loads(capsys.readouterr().out)["variables"]}


def test_the_repository_supplies_the_variable_the_profile_declares(tmp_path, capsys):
    repo = _repo(tmp_path / "repo")
    variables = _env(capsys, "--repo", str(repo))
    assert Path(variables[VARIABLE]["value"]) == (repo / "tutorials").resolve()
    assert os.environ[VARIABLE] == str((repo / "tutorials").resolve())


def test_a_source_that_is_not_where_the_profile_finds_it_is_refused(tmp_path, capsys):
    repo = _repo(tmp_path / "repo", source="elsewhere")
    with pytest.raises(SystemExit):
        main(["env", "--repo", str(repo)])
    error = capsys.readouterr().err
    assert "declares source" in error and "beside the tutorials folder" in error


def test_a_variable_that_disagrees_with_the_repository_is_refused(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    monkeypatch.setenv(VARIABLE, str(tmp_path / "other"))
    with pytest.raises(SystemExit):
        main(["env", "--repo", str(repo)])
    assert f"{VARIABLE}=" in capsys.readouterr().err


def test_the_variable_may_state_what_the_repository_declares(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    monkeypatch.setenv(VARIABLE, str(repo / "tutorials"))
    variables = _env(capsys, "--repo", str(repo))
    assert Path(variables[VARIABLE]["value"]) == (repo / "tutorials")
