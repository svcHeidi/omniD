"""What a caller sees before it knows what to run: the stack's records, one refusal shape, and a cases root that is always supplied."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from omnidriver.cli import main
from omnidriver.core.repository import REPOSITORY_FILE
from plugins.toy import write_toy_native_case

from cli_refusal import refusal

PLUGIN = "plugins.toy:ToyStack"


def _run(capsys, *argv):
    code = main(list(argv))
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture(autouse=True)
def _no_ambient_cases_root(monkeypatch):
    monkeypatch.delenv("OMNIDRIVER_CASES_ROOT", raising=False)


# -- describe with no record lists the stack --------------------------------------


def test_describe_with_no_entry_lists_the_records_the_scripts_and_the_installed_plugins(capsys):
    code, payload = _run(capsys, "describe", "--plugin", PLUGIN)
    assert code == 0
    (record,) = payload["records"]
    assert record["name"] == "toyTutorial" and record["native_case_relpath"] == "toyTutorial"
    assert set(record) == {"name", "native_case_relpath", "axes", "inputs", "serial_only"}
    assert payload["scripts"] == []
    assert payload["installed_plugins"] == sorted(payload["installed_plugins"]) and payload["installed_plugins"]
    assert payload["plugin"]


def test_listing_the_stack_needs_no_cases_root_and_takes_no_preview_flag(capsys):
    assert _run(capsys, "describe", "--plugin", PLUGIN)[0] == 0
    assert "preview a record" in refusal(capsys, ["describe", "--plugin", PLUGIN, "--parallel"])


def test_an_unknown_plugin_lists_the_installed_ids(capsys):
    with mock.patch("omnidriver.cli.discover_plugins", return_value={"alpha": object(), "beta": object()}):
        error = refusal(capsys, ["describe", "--plugin", "nosuch"])
    assert "'nosuch'" in error and "installed plugins: ['alpha', 'beta']" in error


# -- one refusal shape ------------------------------------------------------------


@pytest.mark.parametrize("argv, fragment", [
    ([], "action"),
    (["plan", "--strict"], "--entry or --case is required"),
    (["describe", "--plugin", PLUGIN, "--repo", "."], "omnidriver.toml"),
    (["compare"], "requires --comparison-request and --report"),
])
def test_every_refusal_is_the_same_json_shape_on_stdout(capsys, argv, fragment):
    assert fragment in refusal(capsys, argv)


def test_help_is_still_argparse_output(capsys):
    with pytest.raises(SystemExit) as exit_:
        main(["--help"])
    assert exit_.value.code == 0 and "usage:" in capsys.readouterr().out


# -- a cases root is supplied, never discovered ------------------------------------


def test_a_command_that_needs_a_cases_root_refuses_without_one_by_name(capsys, tmp_path, monkeypatch):
    write_toy_native_case(tmp_path)
    monkeypatch.chdir(tmp_path)
    error = refusal(capsys, ["describe", "--plugin", PLUGIN, "--entry", "toyTutorial"])
    assert "--cases-root" in error and "--repo" in error


def test_a_cases_root_that_is_not_a_folder_is_refused(capsys, tmp_path):
    error = refusal(capsys, ["describe", "--plugin", PLUGIN, "--entry", "toyTutorial", "--cases-root", str(tmp_path / "nowhere")])
    assert "nowhere" in error and "not a directory" in error


def test_a_repository_whose_tutorials_folder_is_missing_is_refused(capsys, tmp_path):
    (tmp_path / REPOSITORY_FILE).write_text(
        f'plugin = "{PLUGIN}"\ntutorials = "tutorials"\nsource = "src"\nscripts = "scripts"\n'
    )
    assert "not a directory" in refusal(capsys, ["describe", "--entry", "toyTutorial", "--repo", str(tmp_path)])


def test_the_environment_variable_still_supplies_the_cases_root(capsys, tmp_path, monkeypatch):
    write_toy_native_case(tmp_path)
    monkeypatch.setenv("OMNIDRIVER_CASES_ROOT", str(tmp_path))
    code, payload = _run(capsys, "describe", "--plugin", PLUGIN, "--entry", "toyTutorial")
    assert code == 0 and payload["entry"]["entry_name"] == "toyTutorial"


@pytest.mark.parametrize("action", ["sweep-plan", "sweep-run"])
def test_a_sweep_takes_its_cases_root_from_its_spec_and_so_needs_none_from_the_command(capsys, action, tmp_path):
    runner = {"sweep-plan": "omnidriver.cli.sweep_plan", "sweep-run": "omnidriver.cli.sweep_run"}[action]
    result = {"case_count": 0, "cases": [], "failed_count": 0}
    with mock.patch(runner, return_value=result):
        code, payload = _run(capsys, action, "--plugin", PLUGIN, "--spec", "s.json", "--output-dir", str(tmp_path / "o"))
    assert code == 0 and payload["status"] == "ok"


# -- the sweep commands report a status --------------------------------------------


def test_a_failed_sweep_says_so_at_the_top_level(capsys, tmp_path):
    with mock.patch("omnidriver.cli.sweep_plan", return_value={"case_count": 1, "cases": [{"status": "failed"}]}):
        code, payload = _run(capsys, "sweep-plan", "--plugin", PLUGIN, "--spec", "s.json", "--output-dir", str(tmp_path / "o"))
    assert code == 1 and payload["status"] == "failed" and payload["case_count"] == 1
    with mock.patch("omnidriver.cli.sweep_run", return_value={"case_count": 1, "failed_count": 1}):
        code, payload = _run(capsys, "sweep-run", "--plugin", PLUGIN, "--spec", "s.json", "--output-dir", str(tmp_path / "o"))
    assert code == 1 and payload["status"] == "failed"


# -- named catalogs are listed by name; the detail is one command away ------------

NAMED = "plugins.toy:NamedCatalogPlugin"


def test_describe_lists_a_catalogs_named_items_by_name_only(tmp_path, capsys):
    write_toy_native_case(tmp_path)
    code, payload = _run(capsys, "describe", "--plugin", NAMED, "--entry", "toyTutorial", "--cases-root", str(tmp_path))
    assert code == 0
    assert payload["plugin_catalogs"] == {"models": {
        "schema_version": "1.0", "models": ["alpha", "beta"], "rules": [{"valid": True}],
    }}


def test_catalog_named_prints_the_catalog_in_full_or_one_item(capsys):
    code, payload = _run(capsys, "catalog", "--plugin", NAMED, "--named", "models")
    assert code == 0 and payload["content"]["models"]["alpha"] == {"states": ["u"], "notes": "n"}
    code, payload = _run(capsys, "catalog", "--plugin", NAMED, "--named", "models", "--item", "beta")
    assert code == 0 and payload["content"] == {"models": {"states": ["v"]}}


def test_a_named_catalog_or_item_that_is_not_there_is_refused_listing_what_is(capsys):
    assert "['models']" in refusal(capsys, ["catalog", "--plugin", NAMED, "--named", "nosuch"])
    assert "no item 'gamma'" in refusal(capsys, ["catalog", "--plugin", NAMED, "--named", "models", "--item", "gamma"])
    assert "--named" in refusal(capsys, ["catalog", "--plugin", NAMED, "--item", "alpha"])
    assert "takes no --entry" in refusal(capsys, ["catalog", "--plugin", NAMED, "--named", "models", "--entry", "x"])
