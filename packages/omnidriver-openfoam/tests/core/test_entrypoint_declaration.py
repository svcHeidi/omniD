"""OpenFOAM's ``Allrun`` spelling is an adapter declaration."""

from __future__ import annotations

from omnidriver.core.plugin_profile import entrypoint_relpaths
from omnidriver.core.tutorial_records import case_folder_record
from omnidriver.core.plugin_interface import load_plugin_context


def test_openfoam_context_declares_allrun() -> None:
    assert entrypoint_relpaths(load_plugin_context("openfoam-environment")) == ("Allrun",)


def test_openfoam_context_runs_an_allrun_case_folder_as_a_record(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")

    record, cases_root = case_folder_record(case, driver_context=load_plugin_context("openfoam-environment"))
    assert cases_root == tmp_path
    assert [step.command for step in record.workflow_steps] == [("Allrun",)]
