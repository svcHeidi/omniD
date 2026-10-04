"""The ``omnidriver build`` example AGENT_GUIDE.md shows builds a case that passes the rules."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.case_builder import build
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_GUIDE = Path(__file__).resolve().parents[3] / "AGENT_GUIDE.md"

pytestmark = pytest.mark.skipif(not _GUIDE.is_file(), reason="AGENT_GUIDE.md is not beside the packages")


def _example_flags() -> dict[str, dict[str, str]]:
    block = re.search(r"^omnidriver build .*?(?<!\\)\n", _GUIDE.read_text(), re.S | re.M).group(0)
    words = shlex.split(block.replace("\\\n", " "))
    flags: dict[str, dict[str, str]] = {"--select": {}, "--set": {}, "--option": {}}
    for flag, value in zip(words, words[1:]):
        if flag in flags:
            name, _equals, text = value.partition("=")
            flags[flag][name] = text
    return flags


def test_the_guides_build_example_builds_a_case_that_breaks_no_rule(tmp_path):
    flags = _example_flags()
    assert "$ELECTRO_MODEL_COEFFS.externalStimulus.stimulusLocationMax" in flags["--set"]
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:guide_build")
    result = build(
        context, tmp_path / "case", select=flags["--select"], set_values=flags["--set"], options=flags["--option"],
        overwrite=False,
    )
    assert result["status"] == "ok", result
