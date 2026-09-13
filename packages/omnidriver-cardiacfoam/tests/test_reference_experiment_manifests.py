"""The selected reference fixtures are narrow, explicit experiment inputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).parent / "fixtures" / "reference_experiments"
_SOURCE_REVISION = "6515739bd1b1c6cf7ef21fe1d4e25830352ed4d2"


@pytest.mark.parametrize(
    "name, expected_case",
    [
        ("single_cell_tworld.json", "tutorials/electrophysiologyProtocols/singleCell"),
        (
            "niederer_tissue.json",
            "tutorials/NiedererEtAl2011/NiedererEtAl2011verification",
        ),
    ],
)
def test_reference_fixture_declares_inputs_and_solver_owned_checker(
    name: str, expected_case: str
) -> None:
    payload = json.loads((_FIXTURES / name).read_text())

    assert payload["schema_version"] == 1
    assert payload["input_policy"] == "committed"
    assert payload["reference"]["source_revision"] == _SOURCE_REVISION
    assert payload["reference"]["source_case_root"] == expected_case
    checker = payload["reference"]["checker"]
    assert checker["availability"] == "available"
    assert checker["mode"] == "check-only"
    assert checker["path"] == "regression/regressionTest.sh"
    assert checker["reference_data"].startswith("regression/")
    assert checker["report_path"].startswith("regression/")
    integration = payload["integration"]
    assert integration["driver_command"][:6] == [
        "{python}", "-m", "omnidriver", "run", "--plugin", "cardiacfoam",
    ]
    assert integration["driver_command"][-2:] == ["--environment-bashrc", "{openfoam_bashrc}"]
    assert integration["solver_checker_command"] == [
        "bash",
        "regression/regressionTest.sh",
        "--check-only",
        "--report",
        checker["report_path"],
    ]
    assert integration["timeout_s"] == 3600
    assert payload["inputs"]
    assert all(item["source"].startswith(expected_case + "/") for item in payload["inputs"])
    assert all(item["destination"].startswith("case/") for item in payload["inputs"])
