"""The native-test harness shared by the conformance checks and every solver's native tests."""
from __future__ import annotations

import pytest

from omnidriver.conformance import (
    NativeEnvironmentError, only_missing, record_run, record_sweep, require_commands, supplied_tree,
)
from plugins.conformance_toy import TOY_PLUGIN, write_toy_native_case


def test_a_tree_that_is_not_supplied_is_a_failure_naming_the_variable(monkeypatch, tmp_path):
    monkeypatch.delenv("TOY_TREE", raising=False)
    with pytest.raises(NativeEnvironmentError, match="TOY_TREE is not set"):
        supplied_tree("TOY_TREE")
    monkeypatch.setenv("TOY_TREE", str(tmp_path / "absent"))
    with pytest.raises(NativeEnvironmentError, match="not a directory"):
        supplied_tree("TOY_TREE")
    monkeypatch.setenv("TOY_TREE", str(tmp_path))
    assert supplied_tree("TOY_TREE") == tmp_path
    with pytest.raises(NativeEnvironmentError, match="has no marker.txt"):
        supplied_tree("TOY_TREE", contains="marker.txt")
    (tmp_path / "marker.txt").write_text("")
    assert supplied_tree("TOY_TREE", contains="marker.txt") == tmp_path


def test_a_command_that_is_not_on_path_is_named(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(NativeEnvironmentError, match=r"\['touch'\]"):
        require_commands("touch")


def test_a_record_runs_through_the_cli_and_hands_back_its_document(tmp_path):
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    run = record_run(
        tmp_path / "work", plugin=TOY_PLUGIN, record="toyTutorial", cases_root=cases_root,
        sweep={"number_cells": [2]},
    )
    assert (run.case_root / "solved.marker").is_file()
    assert run.document["resolvedEntry"]["entry"] == "toyTutorial"
    with pytest.raises(ValueError):
        run.artifact("no-such-format")


def test_a_sweep_whose_case_fails_is_a_failure(tmp_path):
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    with pytest.raises(AssertionError, match="sweep-run"):
        record_sweep(
            tmp_path / "work", plugin=TOY_PLUGIN, record="toyTutorial", cases_root=cases_root,
            sweep={"cell_count": [2]},
        )


_LAT = "out/init_acts_vm_act-thresh.dat"
_BASE = {"status": "failed", "materialization_error": None, "plan_error": None, "timeout_error": None}


def _case(*missing, **overrides):
    return {**_BASE, **overrides, "artifact_reconciliation": {
        "missing_count": len(missing),
        "artifacts": [{"predicted_path": path, "status": "missing"} for path in missing],
    }}


def test_only_a_listed_artifact_missing_is_tolerated():
    assert only_missing(_case(_LAT), [_LAT])
    assert not only_missing(_case("out/vm.igb"), [_LAT])
    assert not only_missing(_case(_LAT, "out/vm.igb"), [_LAT])
    assert not only_missing(_case(_LAT, status="completed"), [_LAT])
    assert not only_missing(_case(_LAT, materialization_error="boom"), [_LAT])
    assert not only_missing(_case(), [_LAT])
