"""OpenFOAM's ``Allrun`` spelling is an adapter declaration."""

from __future__ import annotations

from omnidriver.core.plugin_profile import entrypoint_relpaths
from omnidriver.core.runtime import registry
from omnidriver.openfoam.environment import openfoam_environment_context


def test_openfoam_context_declares_allrun() -> None:
    assert entrypoint_relpaths(openfoam_environment_context()) == ("Allrun",)


def test_openfoam_context_recognizes_an_allrun_case(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")

    context = openfoam_environment_context()
    assert registry._is_case_directory(case, context) is True
    assert registry._case_is_runnable(case, driver_context=context) is True
