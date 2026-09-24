"""Regression coverage for plugin-aware CLI config loading."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from omnidriver import cli
from omnidriver.cli import _load_spec_overrides
from omnidriver.core.runtime.sweep_runner import MaterializedEntry


def test_direct_config_uses_the_selected_plugin_context(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"number_cells": [10]}))
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            tutorials=SimpleNamespace(catalog=lambda: {"registered_tutorials": ()})
        )
    )

    assert _load_spec_overrides(
        str(config_path),
        "manufacturedBidomain",
        driver_context=context,
    ) == {"number_cells": [10]}


def test_execution_materializes_registered_entry_before_final_plan(tmp_path: Path) -> None:
    report = SimpleNamespace(
        status="ok",
        environment_diagnostics=(),
        simulation_audit=(),
        workflow_dag={"steps": []},
        workflow_state=SimpleNamespace(),
        launch={
            "case_root": str(tmp_path / "case"),
            "output_dir": str(tmp_path / "output"),
            "setup_root": str(tmp_path / "setup"),
        },
        expected_artifacts=(),
    )
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            environment_preflight=SimpleNamespace(load=lambda **_kwargs: {}),
        )
    )

    with mock.patch.object(cli, "strict_plan", return_value=report) as strict_plan, \
         mock.patch.object(
             cli,
             "_materialize_entry_case",
             return_value=MaterializedEntry(
                 "registeredTutorial", {"cases_root": str(tmp_path)},
             ),
         ) as materialize, \
         mock.patch.object(cli, "is_launchable", return_value=SimpleNamespace(structural_ok=True)), \
         mock.patch.object(cli, "repo_root_or_none", return_value=None):
        execution, code = cli._context_from_entry(
            selected_entry="registeredTutorial",
            entry_kind="registered_tutorial",
            overrides={"cases_root": str(tmp_path)},
            config_path=str(tmp_path / "config.json"),
            explicit_bashrc=None,
            driver_context=context,
            stage_for_execution=True,
        )

    assert code == 0
    assert execution is not None
    materialize.assert_called_once_with(
        "registeredTutorial",
        {"cases_root": str(tmp_path)},
        driver_context=context,
    )
    assert strict_plan.call_count == 2
    assert strict_plan.call_args.kwargs["overrides"] == {"cases_root": str(tmp_path)}


@pytest.mark.parametrize("wrapped", [False, True], ids=["flat", "entry-section"])
def test_config_supplied_cases_root_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], wrapped: bool,
) -> None:
    # `cases_root` is a real make_spec keyword, so it reads as a valid config
    # key -- but resolve_cases_root has no config-file tier (explicit ->
    # OMNIDRIVER_CASES_ROOT -> cwd, ENVIRONMENT_CONTRACT.md §12). It used to be
    # accepted and then silently overwritten by that chain; it must be refused
    # instead, naming the two supported ways to supply it.
    section = {"cases_root": str(tmp_path / "elsewhere"), "number_cells": [10]}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"someEntry": section} if wrapped else section))
    context = SimpleNamespace(
        capabilities=SimpleNamespace(
            tutorials=SimpleNamespace(catalog=lambda: {"registered_tutorials": ()})
        )
    )

    with mock.patch(
        "omnidriver.core.plugin_interface.default_driver_context", return_value=context,
    ), mock.patch.object(cli, "describe_entry", return_value={}) as describe_entry:
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["describe", "--entry", "someEntry", "--config", str(config_path)])

    assert excinfo.value.code == 2
    stderr = capsys.readouterr().err
    assert "cases_root" in stderr
    assert "--cases-root" in stderr
    assert "OMNIDRIVER_CASES_ROOT" in stderr
    describe_entry.assert_not_called()
