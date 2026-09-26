"""Every native study of every cardiacFOAM tutorial record expands through
its own entry point: ``sweep_plan`` over the study file, the way an agent
runs it, with every case planned ``ok``.

Added 2026-09-26 (review 54b). The 5.4b wave proved its rewritten studies
with one hand-built case per study passed straight to ``strict_plan``,
which bypasses a study's own expansion. Five of fifteen studies could not
run at all: niederer2011's two named no ``cases_root`` (I1), and three of
bidomain's derived a case id with a space in it (I2). This test would have
failed on both. It also replaces
``test_manufactured_solution_axes.py::test_every_cardiac_record_resolves_each_of_its_axis_names_to_its_own_contract``,
which resolved each record's axis names against the same record's axes and
so could fail only on a duplicate (review 54b M3): here every bare name a
real study uses must resolve in its record, and every value must plan.

A study states ``"cases_root": "tutorials"``, relative to the native
repository root (every record study in the tree does), so the sweep runs
from the parent of ``OMNIDRIVER_NATIVE_TUTORIALS``, as the native READMEs'
commands do. Planning stages each case into ``tmp_path``; nothing is
written into the native tree and no solver runs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cardiacfoam_native import native_tutorials_root
from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.sweep_runner import sweep_plan

pytestmark = pytest.mark.native


def _record_studies(tutorials: Path, record) -> list[Path]:
    """The study files under the record's native case that name it."""
    studies_root = tutorials / record.native_case_relpath / "setup" / "studies"
    found = []
    for path in sorted(studies_root.rglob("*.json")):
        spec = json.loads(path.read_text())
        if isinstance(spec, dict) and spec.get("base", {}).get("entry") == record.name:
            found.append(path)
    return found


def _plan_errors(plan: dict) -> list:
    """Every error-level diagnostic of a non-ok plan, so a failure names why."""
    return [
        diagnostic for key, value in plan.items() if key.endswith("_diagnostics") and isinstance(value, list)
        for diagnostic in value if isinstance(diagnostic, dict) and diagnostic.get("severity") == "error"
    ] or [f"status {plan.get('status')!r}"]


@pytest.mark.parametrize("record_name", sorted(TUTORIAL_RECORDS))
def test_every_native_study_of_the_record_plans_every_case(record_name, tmp_path, monkeypatch):
    tutorials = native_tutorials_root()
    record = TUTORIAL_RECORDS[record_name]
    studies = _record_studies(tutorials, record)
    assert studies, f"no native study under {record.native_case_relpath}/setup/studies names {record_name!r}"
    monkeypatch.chdir(tutorials.parent)
    context = load_plugin_context("cardiacfoam")
    problems = []
    for index, study in enumerate(studies):
        relpath = study.relative_to(tutorials).as_posix()
        try:
            result = sweep_plan(study, output_dir=tmp_path / f"study{index}", driver_context=context)
        except ValueError as exc:  # the sweep refused as a whole (TutorialRecordError, SweepValidationError)
            problems.append(f"{relpath}: refused: {type(exc).__name__}: {exc}")
            continue
        if result.get("spec_error") or not result["cases"]:
            problems.append(f"{relpath}: {result.get('spec_error') or 'no cases'}")
            continue
        for case in result["cases"]:
            if case["status"] != "ok":
                detail = case.get("materialization_error") or _plan_errors(case["plan"])
                problems.append(f"{relpath}: case {case['case_id']}: {detail}")
    assert not problems, "\n".join(problems)
