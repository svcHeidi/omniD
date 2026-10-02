"""OpenFOAM's ``Allrun`` spelling is an adapter declaration."""

from __future__ import annotations

from omnidriver.core.plugin_profile import entrypoint_relpaths
from omnidriver.core.tutorial_records import case_folder_record
from omnidriver.openfoam.environment import openfoam_environment_context


def test_openfoam_context_declares_allrun() -> None:
    assert entrypoint_relpaths(openfoam_environment_context()) == ("Allrun",)


def test_openfoam_context_runs_an_allrun_case_folder_as_a_record(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")

    record, cases_root = case_folder_record(case, driver_context=openfoam_environment_context())
    assert cases_root == tmp_path
    assert [step.command for step in record.workflow_steps] == [("Allrun",)]
