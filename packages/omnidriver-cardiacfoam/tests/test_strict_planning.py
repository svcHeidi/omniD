"""Strict planning against the real cardiacFoam tutorials and C++ source.
``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered: these tests fail, not skip, without it.
Only ``constant/`` and ``system/`` are staged into scratch, never the (multi-gigabyte) ``setup/`` sweep tree.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from omnidriver.core.strict_planning import strict_plan

pytestmark = pytest.mark.native

CARDIAC_PLUGIN = CardiacFoamPlugin()
CARDIAC_MAPPING = CARDIAC_PLUGIN.get_profile().cxx_mapping

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CARDIAC_PLUGIN, source="test:strict_planning")

_SINGLE_CELL_RELPATH = "electrophysiologyProtocols/singleCell"
_CABLE_1D_CV_CONVERGENCE_RELPATH = "electrophysiologyProtocols/cableProtocol/monodomain1DCableCV"


def _native_tutorials_root() -> Path:
    """Copied, not imported: each native module is collected with no import-time dependency on a sibling."""
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _stage_case_dictionaries(native_root: Path, relpath: str, scratch_cases_root: Path) -> None:
    """Copy only ``constant/`` and ``system/`` of a native case: all a non-swept ``strict_plan`` reads."""
    native_case = native_root / relpath
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")
    scratch_case = scratch_cases_root / relpath
    scratch_case.mkdir(parents=True, exist_ok=True)
    for name in ("constant", "system"):
        src = native_case / name
        if src.is_dir():
            shutil.copytree(src, scratch_case / name)


def _record_with_steps(name: str, *steps: WorkflowStep) -> TutorialRecord:
    return TutorialRecord(name=name, native_case_relpath=name, workflow_steps=steps)


def test_cli_plan_strict_prints_json_and_returns_zero(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "plan", "--strict", "--entry", "singleCell",
            "--cases-root", str(cases_root),
            "--scratch-dir", str(tmp_path / "scratch"),
        ])

    payload = json.loads(out.getvalue())
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["launch"]["command"]


def test_strict_plan_status_ignores_environment_only_errors(tmp_path: Path, monkeypatch, real_preflight) -> None:
    monkeypatch.delenv("WM_PROJECT_DIR", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *_, **__: f"/usr/bin/{name}" if name == "cardiacFoam" else None,
    )

    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    report = strict_plan(
        "singleCell", environment_source="/no/such/openfoam/bashrc", driver_context=_CTX,
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
    )
    payload = report.to_json()

    assert payload["status"] == "ok"
    assert payload["run_document"]["status"] == "planned"
    assert payload["run_document"]["validation"]["status"] == "ok"
    assert payload["readiness_score"]["status"] == "blocked"
    assert "environment_preflight" in payload["readiness_score"]["blocked_stages"]
    assert any(
        item["code"] == "missing_openfoam_env"
        for item in payload["environment_diagnostics"]
    )


def test_cli_run_strict_refuses_environment_errors_before_execution(tmp_path: Path, monkeypatch, real_preflight) -> None:
    monkeypatch.delenv("WM_PROJECT_DIR", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *_, **__: f"/usr/bin/{name}" if name == "cardiacFoam" else None,
    )

    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "run",
            "--strict",
            "--entry",
            "singleCell",
            "--cases-root", str(cases_root),
            "--scratch-dir", str(tmp_path / "scratch"),
            "--environment-source",
            "/no/such/openfoam/bashrc",
        ])

    payload = json.loads(out.getvalue())
    assert code == 1
    assert payload["status"] == "failed"
    assert payload["error"] == "Execution environment preflight failed."
    assert any(
        item["code"] == "missing_openfoam_env"
        for item in payload["environment_diagnostics"]
    )


def test_strict_plan_fails_on_unknown_workflow_command(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    case_root = cases_root / "badCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "system").mkdir()
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")
    (case_root / "constant" / "electroProperties").write_text(
        "myocardiumSolver singleCellSolver;\n"
        "singleCellSolverCoeffs\n"
        "{\n"
        "    ionicModel AlievPanfilov;\n"
        "    tissue myocyte;\n"
        "    solutionAlgorithm explicit;\n"
        "}\n"
    )
    for name in ("controlDict", "fvSchemes", "fvSolution"):
        (case_root / "system" / name).write_text("\n")

    report = strict_plan(
        _record_with_steps("badCase", WorkflowStep(step_id="unknown", command=("notARealUtility",))),
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
        driver_context=_CTX,
    )

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert any(
        item["code"] == "unknown_workflow_command"
        for item in payload["artifact_diagnostics"]
    )


def test_strict_plan_fails_for_a_solver_no_artifact_handler_covers(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    case_root = cases_root / "missingArtifacts"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "system").mkdir()
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")
    (case_root / "constant" / "electroProperties").write_text(
        "myocardiumSolver futureSolver;\n"
        "futureSolverCoeffs\n"
        "{\n"
        "    ionicModel AlievPanfilov;\n"
        "}\n"
    )
    for name in ("controlDict", "fvSchemes", "fvSolution"):
        (case_root / "system" / name).write_text("\n")

    report = strict_plan(
        _record_with_steps("missingArtifacts", WorkflowStep(step_id="solve", command=("cardiacFoam",))),
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
        driver_context=_CTX,
    )

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert any(
        item["code"] == "unknown_solver" and item["field"] == "myocardiumSolver"
        for item in payload["artifact_diagnostics"]
    )


def test_every_strict_plan_scans_the_supplied_source(tmp_path: Path) -> None:
    """With the source supplied, the catalogue diagnostics are the scan's:
    no contradiction, and only ``uncatalogued`` notes."""
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    report = strict_plan(
        "singleCell", driver_context=_CTX,
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
    ).to_json()
    catalogue = [
        d for d in report["plugin_diagnostics"]
        if d["code"].startswith(("plugin_catalog_", "plugin_cxx_"))
    ]
    assert {(d["level"], d["code"]) for d in catalogue} <= {("info", "plugin_catalog_uncatalogued")}


def test_batched_ionic_model_does_not_require_optional_batched_keys(tmp_path: Path):
    """Both keys are read via lookupOrDefault; the batched model is set explicitly since the native default is Stewart, with a tissue it accepts."""
    report = strict_plan(
        "cable1DCVConvergence", driver_context=_CTX,
        overrides={
            "cases_root": str(_native_tutorials_root()),
            "constant/electroProperties:monodomainSolverCoeffs.ionicModel": "TWorldcompactBatched",
            "constant/electroProperties:monodomainSolverCoeffs.tissue": "epicardialCells",
        },
        scratch_root=str(tmp_path / "scratch"),
    ).to_json()
    errors = [
        d for d in report["run_document"]["validation"].get("diagnostics", [])
        if d.get("level") == "error"
    ]
    assert errors == [], f"unexpected validation errors: {errors}"


def test_absent_stimulus_block_is_not_invented_from_defaults():
    """stimulusIO.C returns a no-op protocol when ``singleCellStimulus`` is absent, so no stimulus is legal."""
    from omnidriver.cardiacfoam.dict_builder import (
        build_electro_properties,
        parse_electro_properties,
    )

    committed = (
        _native_tutorials_root()
        / _SINGLE_CELL_RELPATH
        / "constant/electroProperties"
    )
    parsed = parse_electro_properties(committed)
    without_stimulus = {
        k: v for k, v in parsed["overrides"].items()
        if "singleCellStimulus" not in k
    }

    text = build_electro_properties(parsed["selectors"], overrides=without_stimulus)

    invented = [
        line.strip() for line in text.splitlines()
        if any(k in line for k in ("stim_start", "stim_duration",
                                   "stim_amplitude", "stim_period", "nstim"))
    ]
    assert not invented, (
        "builder invented a stimulus the case did not ask for:\n  "
        + "\n  ".join(invented)
    )
