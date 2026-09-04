"""A case is identified by its path, not by a name under a root.

registry._is_case_directory() already answers "is this a runnable case?" from
a directory's own contents, through the plugin's declared marker or entrypoint
contract -- and it takes a path. Before this, resolve_entry() rejected that
same path and only resolved once the caller split it into a root and a name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.registry import resolve_entry

from plugins.neutral_environment_plugin import NeutralEnvironmentPlugin


def _case(tmp_path: Path, name: str = "mycase") -> Path:
    """A directory the NeutralEnvironmentPlugin's profile calls a case."""
    case = tmp_path / name
    (case / "system").mkdir(parents=True)
    (case / "constant").mkdir()
    (case / "system" / "controlDict").write_text("")
    (case / "Allrun").write_text("#!/bin/sh\nexit 0\n")
    return case


def test_an_absolute_path_resolves_as_a_case(tmp_path: Path) -> None:
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    case = _case(tmp_path)

    resolution = resolve_entry(str(case), entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"
    assert Path(resolution["factory_overrides"]["cases_root"]) == tmp_path
    assert resolution["factory_overrides"]["case_dir_name"] == "mycase"


def test_a_relative_path_resolves_against_the_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    _case(tmp_path)
    monkeypatch.chdir(tmp_path)

    resolution = resolve_entry("mycase", entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"


def test_a_directory_that_is_not_a_case_is_still_refused(tmp_path: Path) -> None:
    """The contrast is the point: if any path resolved, the assertions above
    would pass for a directory with nothing in it."""
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    empty = tmp_path / "notacase"
    empty.mkdir()

    with pytest.raises(KeyError):
        resolve_entry(str(empty), entry_kind="case_folder", driver_context=ctx)


def test_listing_an_empty_directory_returns_nothing(tmp_path: Path) -> None:
    """Zero results is a legitimate answer to "what cases are here", and must
    not be a RuntimeError. Before this, core walked up from its own __file__
    looking for repository markers and raised when it found none."""
    from omnidriver.core.runtime.registry import list_case_directories

    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    assert list_case_directories(tmp_path, driver_context=ctx) == []


def test_core_exposes_no_ambient_root_default() -> None:
    """core.specs.paths must not offer a function that invents a root."""
    from omnidriver.core.specs import paths

    assert not hasattr(paths, "tutorials_root_default")


def test_scratch_is_workspace_local_not_repository_local(tmp_path: Path) -> None:
    """`.tmp/driverfoam` wrote inside the repository, which fails on a
    read-only install and is solver-branded. It is workspace-local now --
    deliberately NOT the OS temp directory, because sweep outputs default here
    and having the OS reap them would be worse than the old behaviour."""
    from omnidriver.core.specs.paths import default_sweep_output_dir, scratch_root

    assert scratch_root(tmp_path) == tmp_path / ".omnidriver"
    out = default_sweep_output_dir("study.json", base=tmp_path)
    assert out == tmp_path / ".omnidriver" / "sweeps" / "study"


def test_scratch_honours_the_environment_variable(tmp_path: Path, monkeypatch) -> None:
    from omnidriver.core.specs.paths import scratch_root

    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "elsewhere"))
    assert scratch_root(tmp_path) == tmp_path / "elsewhere"
