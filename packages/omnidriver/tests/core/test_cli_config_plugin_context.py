"""Regression coverage for plugin-aware CLI config loading."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from omnidriver import cli
from omnidriver.cli import _load_spec_overrides


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
             return_value={"cases_root": str(tmp_path)},
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
