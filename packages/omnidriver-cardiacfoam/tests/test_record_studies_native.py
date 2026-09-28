"""Every native study of every cardiacFOAM tutorial record plans every case ``ok`` through ``sweep_plan``, as an agent runs it.

Studies state ``"cases_root": "tutorials"`` relative to the native repository root, so the sweep runs from the parent of
``OMNIDRIVER_NATIVE_TUTORIALS``."""
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
