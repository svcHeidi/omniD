"""The selected reference fixtures are narrow, explicit experiment inputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_FIXTURES = Path(__file__).parent / "fixtures" / "reference_experiments"
_SOURCE_REVISION = "98afac41a8c3e3de1ef1067b7e5f1d5ca4349cb0"


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
    assert checker["availability"] == "pending-solver-check-only-interface"
    assert checker["mode"] == "check-only"
    assert checker["path"] == "regression/regressionTest.sh"
    assert checker["reference_data"].startswith("regression/")
    assert checker["report_path"].startswith("regression/")
    assert payload["inputs"]
    assert all(item["source"].startswith(expected_case + "/") for item in payload["inputs"])
    assert all(item["destination"].startswith("case/") for item in payload["inputs"])
