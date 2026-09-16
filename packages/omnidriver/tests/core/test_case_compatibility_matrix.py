"""Existing-case discovery through Core-owned entrypoint rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.registry import list_entries

from plugins.minimal_plugin import MinimalTestPlugin

_CTX = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-compatibility")


def _touch(case_root: Path, relative: str) -> None:
    path = case_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


@pytest.mark.parametrize(
    ("files", "discovered", "runnable"),
    [
        ((), False, False),
        (("run-case",), True, True),
    ],
)
def test_existing_case_discovery_and_runnability_matrix(
    tmp_path: Path,
    files: tuple[str, ...],
    discovered: bool,
    runnable: bool,
) -> None:
    case_root = tmp_path / "candidate"
    case_root.mkdir()
    for relative in files:
        _touch(case_root, relative)

    matches = [
        entry for entry in list_entries(tmp_path, driver_context=_CTX)
        if entry["entry_name"] == "candidate"
    ]
    assert bool(matches) is discovered
    if discovered:
        assert matches[0]["is_runnable"] is runnable


@pytest.mark.parametrize("authored_directory", ("postProcessing", "logs"))
def test_neutral_environment_does_not_hide_authored_directory_names(
    tmp_path: Path,
    authored_directory: str,
) -> None:
    """Only an environment may declare which generated roots discovery skips."""
    case_root = tmp_path / authored_directory / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "run-case")
    context = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:neutral-discovery")

    entries = list_entries(tmp_path, driver_context=context)

    assert [entry["entry_path"] for entry in entries] == [
        f"{authored_directory}/nestedCase",
    ]


def test_neutral_environment_does_not_assume_a_parallel_output_prefix(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    _touch(case_root, "run-case")
    context = driver_context(
        MinimalTestPlugin(entrypoint="run-case"), source="test:neutral-decomposition",
    )

    assert [entry["entry_path"] for entry in list_entries(tmp_path, driver_context=context)] == [
        "processor0/nestedCase",
    ]
