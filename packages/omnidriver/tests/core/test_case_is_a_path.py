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

from plugins.minimal_plugin import MinimalTestPlugin


def _case(tmp_path: Path, name: str = "mycase") -> Path:
    """A directory with the test's explicitly declared entrypoint."""
    case = tmp_path / name
    case.mkdir(parents=True)
    (case / "run-case").write_text("#!/bin/sh\n")
    (case / "run-case").write_text("#!/bin/sh\nexit 0\n")
    return case


def test_an_absolute_path_resolves_as_a_case(tmp_path: Path) -> None:
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    case = _case(tmp_path)

    resolution = resolve_entry(str(case), entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"
    assert Path(resolution["factory_overrides"]["cases_root"]) == tmp_path
    assert resolution["factory_overrides"]["case_dir_name"] == "mycase"


def test_a_relative_path_resolves_against_the_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    _case(tmp_path)
    monkeypatch.chdir(tmp_path)

    resolution = resolve_entry("mycase", entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"


def test_a_conflicting_case_dir_name_is_refused_not_dropped(tmp_path: Path) -> None:
    """The path already names the case, so a supplied `case_dir_name` that
    differs is a contradiction. It used to be overwritten by the path's own
    name without a word -- a `--config` value vanished, and a case-path sweep
    entry's staged name was discarded so the source case was mutated in
    place. Same defect shape as the config-supplied `cases_root` refusal."""
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    case = _case(tmp_path)

    with pytest.raises(ValueError, match="case_dir_name") as excinfo:
        resolve_entry(
            str(case),
            entry_kind="case_folder",
            overrides={"case_dir_name": "someOtherName"},
            driver_context=ctx,
        )
    assert "someOtherName" in str(excinfo.value)
    assert "mycase" in str(excinfo.value)


def test_a_case_dir_name_that_restates_the_path_is_accepted(tmp_path: Path) -> None:
    """The contrast: refusing every supplied value would also pass the test
    above. Only a contradiction is refused."""
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    case = _case(tmp_path)

    resolution = resolve_entry(
        str(case),
        entry_kind="case_folder",
        overrides={"case_dir_name": "mycase"},
        driver_context=ctx,
    )

    assert resolution["factory_overrides"]["case_dir_name"] == "mycase"


def test_a_directory_that_is_not_a_case_is_still_refused(tmp_path: Path) -> None:
    """The contrast is the point: if any path resolved, the assertions above
    would pass for a directory with nothing in it."""
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    empty = tmp_path / "notacase"
    empty.mkdir()

    with pytest.raises(KeyError):
        resolve_entry(str(empty), entry_kind="case_folder", driver_context=ctx)


def test_listing_an_empty_directory_returns_nothing(tmp_path: Path) -> None:
    """Zero results is a legitimate answer to "what cases are here", and must
    not be a RuntimeError. Before this, core walked up from its own __file__
    looking for repository markers and raised when it found none."""
    from omnidriver.core.runtime.registry import list_case_directories

    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path")
    assert list_case_directories(tmp_path, driver_context=ctx) == []


def test_core_exposes_no_ambient_root_default() -> None:
    """core.specs.paths must not offer a function that invents a root."""
    from omnidriver.core.specs import paths

    assert not hasattr(paths, "tutorials_root_default")


def test_scratch_is_supplied_not_repository_or_workspace_local(tmp_path: Path, monkeypatch) -> None:
    """`.tmp/driverfoam` wrote inside the repository, which fails on a
    read-only install and is solver-branded. It then became workspace-local,
    ``<cases_root>/.omnidriver`` -- which wrote into native tutorials trees.
    Corrected 2026-09-26 (owner decision): it is supplied or refused, never
    defaulted -- still deliberately NOT the OS temp directory, because sweep
    outputs default under it and having the OS reap them would be worse."""
    from omnidriver.core.specs.paths import (
        ScratchRootNotSupplied, default_sweep_output_dir, resolve_scratch_root,
    )

    monkeypatch.delenv("OMNIDRIVER_SCRATCH_DIR", raising=False)
    with pytest.raises(ScratchRootNotSupplied):
        resolve_scratch_root(None)
    with pytest.raises(ScratchRootNotSupplied):
        default_sweep_output_dir("study.json", scratch_root=None)
    out = default_sweep_output_dir("study.json", scratch_root=tmp_path / "scratch")
    assert out == tmp_path / "scratch" / "sweeps" / "study"


def test_scratch_honours_the_environment_variable(tmp_path: Path, monkeypatch) -> None:
    from omnidriver.core.specs.paths import resolve_scratch_root

    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "elsewhere"))
    assert resolve_scratch_root(None) == tmp_path / "elsewhere"
