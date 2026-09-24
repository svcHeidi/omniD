"""A case-path sweep entry is mutated in its staged copy, never at its source.

``_materialize_entry_case`` stages the entry's case under ``staging_root`` and
re-resolves the entry against that copy. For a registered tutorial the second
resolution is steered by ``cases_root``/``case_dir_name``. A case *path* names
its case by the path itself, so those overrides cannot steer it: before
2026-09-24 ``resolve_entry`` overwrote the staged ``case_dir_name`` with the
source's own name, the "test doubles" branch returned the unstaged overrides,
and the source case was mutated in place. Commit 7d672f1 turned that into a
``ValueError``; this module covers the fix, which re-resolves the staged
directory's own path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.sweep_runner import _materialize_entry_case, sweep_plan

from plugins.minimal_plugin import MinimalTestPlugin


class _WritesIntoItsCaseRoot:
    """A mutation that leaves a visible mark in whichever case it is given.

    A generic case with no adapter callback writes nothing, so asserting
    "the source is untouched" against it would pass whatever directory the
    mutation ran in. This one writes, so where it wrote is observable.
    """

    def __init__(self) -> None:
        self.case_roots: list[Path] = []

    def __call__(self, case_root, _case, **_kwargs) -> None:
        self.case_roots.append(Path(case_root))
        (Path(case_root) / "mutated").write_text("yes\n")


def _source_case(tmp_path: Path) -> Path:
    case = tmp_path / "source" / "mycase"
    case.mkdir(parents=True)
    (case / "run-case").write_text("#!/bin/sh\nexit 0\n")
    return case


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_a_case_path_entry_is_mutated_in_its_staged_copy(tmp_path: Path) -> None:
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path-sweep")
    source = _source_case(tmp_path)
    before = _snapshot(source)
    staged = tmp_path / "staging" / "sweep_case_001"
    mutation = _WritesIntoItsCaseRoot()

    # A real callback keeps a generic case on the deprecated, non-reporting
    # apply_case hook (generic_case's module docstring), which says so.
    with pytest.warns(DeprecationWarning, match="apply_case"):
        materialized = _materialize_entry_case(
            str(source),
            # MinimalTestPlugin declares no output convention, so the first
            # (unstaged) resolution needs one supplied.
            {"_apply_case_mutation": mutation, "output_dir_name": "out"},
            staging_root=staged,
            driver_context=ctx,
        )

    assert mutation.case_roots == [staged.resolve()]
    assert (staged / "mutated").is_file()
    assert _snapshot(source) == before
    # Callers plan and run with what is returned, so the entry itself must
    # now be the staged copy -- overrides alone cannot re-point a case path.
    assert materialized.entry == str(staged.resolve())
    assert "case_dir_name" not in materialized.overrides
    assert "cases_root" not in materialized.overrides


def test_sweep_plan_plans_a_case_path_entry_at_its_staged_copy(tmp_path: Path) -> None:
    """Mutating the staged copy is half of it: sweep_plan then plans with the
    entry, and a plan of the source path would run the solver there."""
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test:case-path-sweep")
    source = _source_case(tmp_path)
    before = _snapshot(source)
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps({
        "base": {"entry": str(source), "output_dir_name": "out"},
        "sweep": {"mode": "zip", "independent": {"dimension": ["2D"]}},
    }))
    output_dir = tmp_path / "sweep_out"

    report = sweep_plan(spec_path, output_dir=output_dir, driver_context=ctx)

    [case] = report["cases"]
    assert "materialization_error" not in case, case
    staged = (output_dir / "cases" / case["case_id"]).resolve()
    assert Path(case["plan"]["launch"]["case_root"]).resolve() == staged
    assert _snapshot(source) == before
