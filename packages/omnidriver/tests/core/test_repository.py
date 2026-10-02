"""A solver repository's ``omnidriver.toml`` names its plugin and where its tutorials, source and scripts are."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.repository import (
    REPOSITORY_FILE,
    RepositoryError,
    read_repository,
    repository_of_cases_root,
)
from plugins.toy import write_toy_native_case

PLUGIN = "plugins.toy:ToyStack"
OTHER_PLUGIN = "plugins.toy:NeutralEnvironmentPlugin"


def _repo(root: Path, *, plugin: str = PLUGIN, tutorials: str = "tutorials", **overrides: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    keys = {"plugin": plugin, "tutorials": tutorials, "source": "src", "scripts": "applications/scripts", **overrides}
    (root / REPOSITORY_FILE).write_text("".join(f'{key} = "{value}"\n' for key, value in keys.items()))
    return root


def test_a_repository_file_names_its_plugin_and_three_places_inside_the_repository(tmp_path):
    repository = read_repository(_repo(tmp_path / "repo"))
    root = (tmp_path / "repo").resolve()
    assert (repository.plugin, repository.root) == (PLUGIN, root)
    assert (repository.tutorials, repository.source, repository.scripts) == (
        root / "tutorials", root / "src", root / "applications" / "scripts",
    )


def test_the_tutorials_folder_may_be_the_repository_itself(tmp_path):
    assert read_repository(_repo(tmp_path / "repo", tutorials=".")).tutorials == (tmp_path / "repo").resolve()


@pytest.mark.parametrize("text, message", [
    ('plugin = "p"\ntutorials = "t"\nsource = "s"\n', "missing \\['scripts'\\]"),
    ('plugin = "p"\ntutorials = "t"\nsource = "s"\nscripts = "x"\nextra = "y"\n', "unknown \\['extra'\\]"),
    ('plugin = "p"\ntutorials = "t"\nsource = ""\nscripts = "x"\n', "source must be a non-empty string"),
    ('plugin = "p"\ntutorials = "../elsewhere"\nsource = "s"\nscripts = "x"\n', "tutorials = '../elsewhere' must be a path inside"),
    ('plugin = "p"\ntutorials = "/abs"\nsource = "s"\nscripts = "x"\n', "tutorials = '/abs' must be a path inside"),
    ("not toml [", "cannot read"),
])
def test_an_incomplete_unclear_or_escaping_file_is_refused_by_name(tmp_path, text, message):
    (tmp_path / REPOSITORY_FILE).write_text(text)
    with pytest.raises(RepositoryError, match=message):
        read_repository(tmp_path)


def test_a_missing_file_is_refused_by_name(tmp_path):
    with pytest.raises(RepositoryError, match="cannot read"):
        read_repository(tmp_path)


def test_a_cases_root_belongs_to_the_repository_whose_tutorials_it_is(tmp_path):
    _repo(tmp_path / "foam")
    (tmp_path / "foam" / "tutorials").mkdir()
    _repo(tmp_path / "core", tutorials=".")
    assert repository_of_cases_root(tmp_path / "foam" / "tutorials").root == (tmp_path / "foam").resolve()
    assert repository_of_cases_root(tmp_path / "core").root == (tmp_path / "core").resolve()


def test_a_cases_root_that_is_not_a_repositorys_tutorials_has_no_repository(tmp_path):
    _repo(tmp_path / "repo")
    (tmp_path / "repo" / "tutorials").mkdir()
    (tmp_path / "repo" / "other").mkdir()
    assert repository_of_cases_root(tmp_path / "repo" / "other") is None
    assert repository_of_cases_root(tmp_path) is None


def test_the_file_is_never_searched_for_above_the_supplied_place(tmp_path):
    _repo(tmp_path / "repo")
    deep = tmp_path / "repo" / "tutorials" / "nested" / "deeper"
    deep.mkdir(parents=True)
    assert repository_of_cases_root(deep) is None


# -- the CLI -------------------------------------------------------------------


def _toy_repo(tmp_path: Path, **overrides) -> Path:
    repo = _repo(tmp_path / "repo", **overrides)
    write_toy_native_case(repo / "tutorials")
    return repo


def _describe(capsys, *argv):
    code = main(["describe", "--entry", "toyTutorial", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_repo_selects_the_plugin_and_supplies_the_cases_root(tmp_path, capsys):
    code, payload = _describe(capsys, "--repo", str(_toy_repo(tmp_path)))
    assert code == 0, payload
    assert payload["entry"]["entry_name"] == "toyTutorial"


def test_a_supplied_cases_root_that_is_a_repositorys_tutorials_selects_the_repository(tmp_path, capsys):
    repo = _toy_repo(tmp_path)
    code, payload = _describe(capsys, "--cases-root", str(repo / "tutorials"))
    assert code == 0, payload


def test_the_environment_cases_root_selects_the_repository_too(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OMNIDRIVER_CASES_ROOT", str(_toy_repo(tmp_path) / "tutorials"))
    code, payload = _describe(capsys)
    assert code == 0, payload


def test_plugin_and_repository_that_select_the_same_stack_agree(tmp_path, capsys):
    code, payload = _describe(capsys, "--repo", str(_toy_repo(tmp_path)), "--plugin", PLUGIN)
    assert code == 0, payload


def test_plugin_and_repository_that_select_different_stacks_are_refused_by_name(tmp_path, capsys):
    repo = _toy_repo(tmp_path)
    with pytest.raises(SystemExit):
        main(["describe", "--entry", "toyTutorial", "--repo", str(repo), "--plugin", OTHER_PLUGIN])
    error = capsys.readouterr().err
    assert OTHER_PLUGIN in error and str(repo.resolve() / REPOSITORY_FILE) in error
    assert "capability_digest" in error


@pytest.mark.parametrize("argv", [
    ["describe", "--entry", "toyTutorial"],
    ["describe", "--entry", "toyTutorial", "--cases-root", "."],
])
def test_with_no_plugin_and_no_repository_a_plugin_is_required_by_name(tmp_path, capsys, monkeypatch, argv):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMNIDRIVER_CASES_ROOT", raising=False)
    with pytest.raises(SystemExit):
        main(argv)
    assert "no plugin was selected" in capsys.readouterr().err


def test_the_working_directory_is_never_searched_for_a_repository(tmp_path, capsys, monkeypatch):
    repo = _toy_repo(tmp_path)
    monkeypatch.chdir(repo / "tutorials")
    monkeypatch.delenv("OMNIDRIVER_CASES_ROOT", raising=False)
    with pytest.raises(SystemExit):
        main(["describe", "--entry", "toyTutorial"])
    assert "no plugin was selected" in capsys.readouterr().err


def test_repo_and_cases_root_are_exclusive(tmp_path, capsys):
    repo = _toy_repo(tmp_path)
    with pytest.raises(SystemExit):
        main(["describe", "--entry", "toyTutorial", "--repo", str(repo), "--cases-root", str(repo / "tutorials")])
    assert "--repo supplies the cases root" in capsys.readouterr().err


def test_a_broken_repository_file_is_refused_not_ignored(tmp_path, capsys):
    repo = _toy_repo(tmp_path)
    (repo / REPOSITORY_FILE).write_text('plugin = "x"\n')
    with pytest.raises(SystemExit):
        main(["describe", "--entry", "toyTutorial", "--repo", str(repo), "--plugin", PLUGIN])
    assert "must set exactly" in capsys.readouterr().err
