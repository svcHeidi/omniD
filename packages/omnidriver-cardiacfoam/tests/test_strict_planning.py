"""Strict planning against the real cardiacFoam tutorials and C++ source.

Converted 2026-09-26 (R2 fix, finding M6) from ``skip_without_monorepo`` to
``@pytest.mark.native``: the old gate used ``conftest.cardiacfoam_monorepo_root``
(now ``omnidriver.cardiacfoam.monorepo.cardiacfoam_monorepo_root``), which
walks up from this file looking for ``tutorials/``+``applications/`` siblings
-- a check that can only succeed when this checkout sits *inside* the full
cardiacFoam monorepo. In a standalone ``omnidriver`` checkout it is always
``None``, so this module never ran, not even in the monorepo's own CI. This
module's own edits (A1's ``--openfoam-bashrc`` -> ``--environment-source``
rename) were consequently unverified.

``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never discovered -- this test
FAILS, not skips, when it is unset, the same posture every other
``@pytest.mark.native`` test in this suite takes. A registered tutorial's
case files are staged into a scratch ``cases_root`` per test (never the
native tree itself, which is read-only): only ``constant/`` and ``system/``
are copied, never the (multi-gigabyte, for ``singleCell``) ``setup/`` sweep
tree that a single, non-swept ``strict_plan`` call never reads.

``test_batched_ionic_model_does_not_require_optional_batched_keys`` and
``test_electromechanics_is_advertised_as_not_working_while_it_is_not`` used
``default_driver_context()``, which now raises ``LookupError`` in a checkout
with more than one installed solver-tier plugin (cardiaccore, cardiacfoam,
opencarp all live here) -- there is no unambiguous default any more. Both
now use this module's own explicit ``_CTX``, exactly like every other test
here.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

from omnidriver.core import strict_planning
from omnidriver.cli import main
from omnidriver.openfoam.dict_keys_scanner import (
    compute_dict_key_drift,
    strict_dict_key_report,
)
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.core.runtime.models import CaseConfig, TutorialSpec
from omnidriver.core.strict_planning import strict_plan

pytestmark = pytest.mark.native

CARDIAC_PLUGIN = CardiacFoamPlugin()
CARDIAC_MAPPING = CARDIAC_PLUGIN.get_profile().cxx_mapping

# strict_plan now takes a mandatory driver_context
# (test_core_context_is_explicit.py); this file already builds
# CARDIAC_PLUGIN above, so this reproduces the previous implicit default.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CARDIAC_PLUGIN, source="test:strict_planning")

_SINGLE_CELL_RELPATH = "electrophysiologyProtocols/singleCell"
_MANUFACTURED_BIDOMAIN_RELPATH = "manufacturedSolutions/bidomain"
_CABLE_1D_CV_CONVERGENCE_RELPATH = "electrophysiologyProtocols/cableProtocol/monodomain1DCableCV"
_MANUFACTURED_EM_RELPATH = "manufacturedSolutions/monodomainTotalLagrangianEM"


def _native_tutorials_root() -> Path:
    """Copied (not imported) from other ``@pytest.mark.native`` modules'
    own helper of the same name/shape -- each module is collected
    standalone and intentionally carries no import-time dependency on a
    sibling test module."""
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
    """Copy only ``constant/`` and ``system/`` of a native case into
    ``scratch_cases_root/relpath`` -- everything a non-swept ``strict_plan``
    call reads for one registered tutorial -- never the native tree itself,
    and never its (per-tutorial, sometimes multi-gigabyte) ``setup/`` sweep
    data."""
    native_case = native_root / relpath
    if not native_case.is_dir():
        pytest.fail(f"native fixture case missing: {native_case}")
    scratch_case = scratch_cases_root / relpath
    scratch_case.mkdir(parents=True, exist_ok=True)
    for name in ("constant", "system"):
        src = native_case / name
        if src.is_dir():
            shutil.copytree(src, scratch_case / name)


def _spec_with_workflow(case_root: Path, *, steps: list[dict]) -> TutorialSpec:
    return TutorialSpec(
        name=case_root.name,
        case_root=case_root,
        setup_root=case_root,
        output_dir=case_root / "postProcessing",
        build_cases=lambda: [CaseConfig(case_id="default", params={})],
        apply_case=lambda *_args, **_kwargs: None,
        metadata={
            "entry_name": case_root.name,
            "entry_kind": "case_folder",
            "entry_path": case_root.name,
            "source_type": "filesystem_case",
            "workflow_family": None,
            "workflow_dag": {"steps": steps},
        },
    )


def test_strict_plan_succeeds_for_single_cell(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    report = strict_plan(
        "singleCell", environment_source="/no/such/openfoam/bashrc", driver_context=_CTX,
        overrides={"cases_root": str(cases_root)},
    )
    payload = report.to_json()

    assert payload["status"] == "ok"

    # Updated 2026-09-18. This asserted `score == 100` and `status == "ready"`.
    # The test supplies a deliberately nonexistent bashrc AND runs under a
    # conftest that sets SKIP_ENV_DIAGNOSTICS, so environment preflight never
    # executes -- and it used to be paid its full ten points regardless. This
    # assertion did not fail, it *ratified*: see
    # docs/superpowers/specs/2026-09-18-coverage-as-evidence.md §1.
    #
    # The invariant is asserted rather than a new exact total, deliberately.
    readiness = payload["readiness_score"]
    assert readiness["score"] < 100, (
        "a plan whose environment preflight did not run reports a perfect score"
    )
    assert "environment_preflight" in readiness["uncovered_stages"]
    environment = next(
        item for item in payload["simulation_audit"]
        if item["stage"] == "environment_preflight"
    )
    assert environment["points"] == 0
    assert environment["status"] == "not_requested"

    # Not "ready": `ready` is a success claim, and this plan has a real coverage
    # gap.
    assert readiness["status"] != "ready"
    assert {
        item["stage"] for item in payload["simulation_audit"]
    } == {
        "simulation_generation",
        "case_preparation_files",
        "dictionary_resolution",
        "workflow_preparation",
        "artifact_prediction",
        "environment_preflight",
        "mesh_geometry",
    }
    generation_audit = next(
        item for item in payload["simulation_audit"]
        if item["stage"] == "simulation_generation"
    )
    assert generation_audit["evidence"]["case_count"] >= 1
    assert payload["resolved_entry"]["entry_kind"] == "registered_tutorial"
    assert payload["expected_artifacts"]
    assert payload["run_document"]["version"] == "3"
    assert payload["run_document"]["validation"]["status"] == "ok"
    assert payload["workflow_diagnostics"] == []
    assert payload["workflow_dag"]["schema_version"] == "1"
    assert payload["workflow_dag"]["step_status_values"] == [
        "pending",
        "running",
        "completed",
        "failed",
        "skipped",
    ]
    # Corrected 2026-09-26 (R2 fix, finding M6): this asserted steps[0] was
    # the solve step directly. The real native singleCell case's committed
    # system/blockMeshDict means the planner now also emits a "mesh" step
    # ahead of "solve" -- this module never ran against the real tree before,
    # so that drift was never caught. The solve step itself is unchanged.
    solve_step = next(
        step for step in payload["workflow_dag"]["steps"] if step["id"] == "solve"
    )
    assert solve_step["command"] == "cardiacFoam"
    assert solve_step["args"] == []
    assert solve_step["cwd"] == "."
    assert solve_step["retry_policy"] == {}
    assert {artifact["artifact_id"] for artifact in payload["expected_artifacts"]} <= set(
        solve_step["produces"]
    )
    assert payload["run_document"]["workflowDag"] == payload["workflow_dag"]
    solve_state = next(
        step for step in payload["workflow_state"]["steps"] if step["step_id"] == "solve"
    )
    assert payload["workflow_state"]["status"] == "pending"
    assert payload["workflow_state"]["failed_step_id"] is None
    assert solve_state["status"] == "pending"
    assert solve_state["attempt"] == 0
    assert solve_state["command"] == "cardiacFoam"
    assert solve_state["args"] == []
    assert solve_state["cwd"] == "."
    assert solve_state["exit_code"] is None
    assert solve_state["stdout_log"] is None
    assert solve_state["stderr_log"] is None
    assert payload["run_document"]["workflowState"] == payload["workflow_state"]


def test_strict_plan_succeeds_for_manufactured_tutorial(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _MANUFACTURED_BIDOMAIN_RELPATH, cases_root)
    report = strict_plan(
        "manufacturedBidomain", driver_context=_CTX, overrides={"cases_root": str(cases_root)},
    )
    payload = report.to_json()

    assert payload["status"] == "ok"
    assert payload["workflow_dag"]["steps"]
    # Step count is not asserted here -- run_in_parallel defaults to True and
    # wraps solve with decomposePar/reconstructPar (see parallel_execution.py),
    # so the exact count is an implementation detail of the real committed
    # decomposeParDict, not something this test should hardcode.
    assert [step["status"] for step in payload["workflow_state"]["steps"]] == (
        ["pending"] * len(payload["workflow_dag"]["steps"])
    )
    assert {
        step["step_id"] for step in payload["workflow_state"]["steps"]
    } == {
        step["id"] for step in payload["workflow_dag"]["steps"]
    }
    assert any(
        artifact["artifact_id"] == "verification_error_summary"
        for artifact in payload["expected_artifacts"]
    )


def test_cli_plan_strict_prints_json_and_returns_zero(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    out = StringIO()
    with redirect_stdout(out):
        code = main([
            "--plugin", "cardiacfoam",
            "plan", "--strict", "--entry", "singleCell",
            "--cases-root", str(cases_root),
        ])

    payload = json.loads(out.getvalue())
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["launch"]["command"]


def test_strict_plan_status_ignores_environment_only_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SKIP_ENV_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("WM_PROJECT_DIR", raising=False)
    monkeypatch.setattr(
        strict_planning.shutil,
        "which",
        lambda name, *_, **__: f"/usr/bin/{name}" if name == "cardiacFoam" else None,
    )

    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _SINGLE_CELL_RELPATH, cases_root)
    report = strict_plan(
        "singleCell", environment_source="/no/such/openfoam/bashrc", driver_context=_CTX,
        overrides={"cases_root": str(cases_root)},
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


def test_cli_run_strict_refuses_environment_errors_before_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SKIP_ENV_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("WM_PROJECT_DIR", raising=False)
    monkeypatch.setattr(
        strict_planning.shutil,
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
            # Renamed from --openfoam-bashrc (A1, 2026-09-26): the CLI flag
            # is now solver-neutral.
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


def test_strict_plan_fails_on_unknown_workflow_command() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
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
        with mock.patch.object(
            strict_planning,
            "load_entry_spec",
            return_value=_spec_with_workflow(
                case_root,
                steps=[{"id": "unknown", "command": "notARealUtility", "depends_on": []}],
            ),
        ):
            report = strict_plan(
                "badCase",
                overrides={"cases_root": str(cases_root)}, driver_context=_CTX,)

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert any(
        item["code"] == "unknown_workflow_command"
        for item in payload["artifact_diagnostics"]
    )


def test_strict_plan_fails_on_unknown_workflow_dependency() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
        case_root = cases_root / "badDependency"
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
        with mock.patch.object(
            strict_planning,
            "load_entry_spec",
            return_value=_spec_with_workflow(
                case_root,
                steps=[{"id": "solve", "command": "cardiacFoam", "depends_on": ["mesh"]}],
            ),
        ):
            report = strict_plan(
                "badDependency",
                overrides={"cases_root": str(cases_root)}, driver_context=_CTX,)

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert payload["readiness_score"]["status"] == "blocked"
    assert "workflow_preparation" in payload["readiness_score"]["blocked_stages"]
    workflow_audit = next(
        item for item in payload["simulation_audit"]
        if item["stage"] == "workflow_preparation"
    )
    assert workflow_audit["points"] == 0
    assert payload["run_document"]["status"] == "failed"
    assert payload["run_document"]["validation"]["status"] == "failed"
    assert any(
        item["code"] == "unknown_workflow_dependency"
        for item in payload["workflow_diagnostics"]
    )


def test_strict_plan_fails_when_artifact_prediction_is_empty() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        cases_root = Path(temp_dir)
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
            "missingArtifacts",
            overrides={"cases_root": str(cases_root)}, driver_context=_CTX,)

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert any(
        item["code"] == "empty_artifact_prediction"
        for item in payload["artifact_diagnostics"]
    )


def test_strict_dict_key_scanner_allowlist_is_current() -> None:
    """The committed ``dict_key_allowlist.json`` against the real native
    C++ source (``<OMNIDRIVER_NATIVE_TUTORIALS>/../src``, the tutorials
    tree's own monorepo sibling -- supplied via that one environment
    variable, never independently discovered)."""
    assert CARDIAC_MAPPING is not None
    src_root = _native_tutorials_root().parent / "src"
    if not src_root.is_dir():
        pytest.fail(
            f"expected a 'src' sibling of OMNIDRIVER_NATIVE_TUTORIALS's "
            f"tutorials directory at {src_root}, the native cardiacFOAM "
            f"monorepo's C++ source tree"
        )
    report = strict_dict_key_report(
        src_root,
        allowlist_path=CARDIAC_MAPPING.allowlist_path,
        entries=CARDIAC_PLUGIN.get_dict_entries(),
    )
    assert report.status == "ok"
    assert report.to_json()["unused_allowlist"] == []


def test_strict_dict_key_scanner_fails_on_unallowlisted_key() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        src_root = Path(temp_dir) / "src"
        src_root.mkdir()
        (src_root / "reader.C").write_text(
            'void read(const Foam::dictionary& dict) { dict.lookup("unlistedStrictKey"); }\n'
        )
        drift = compute_dict_key_drift(
            src_root,
            entries=CARDIAC_PLUGIN.get_dict_entries(),
        )
        allowlist_path = Path(temp_dir) / "allowlist.json"
        allowlist_path.write_text(json.dumps({
            "unmatched_cxx_reads": sorted(drift["unmatched_cxx_reads"] - {"unlistedStrictKey"}),
            "stale_paths": sorted(drift["stale_paths"]),
            "unmatched_subdicts": sorted(drift["unmatched_subdicts"]),
        }))

        report = strict_dict_key_report(
            src_root,
            allowlist_path=allowlist_path,
            entries=CARDIAC_PLUGIN.get_dict_entries(),
        )

    payload = report.to_json()
    assert payload["status"] == "failed"
    assert payload["unmatched_cxx_reads"] == ["unlistedStrictKey"]


def test_batched_ionic_model_does_not_require_optional_batched_keys(tmp_path: Path):
    """batchedIntegrator/batchedSubsteps default in C++, so a batched case
    that omits them must still plan cleanly.

    Both are read only via lookupOrDefault -- batchedIonicModel.H:197,200 and
    batchedActiveTensionModel.C:46,48 (defaults 1 and "euler"). The catalog
    nonetheless marked them required_when the ionic model is batched, which
    rejected monodomain1DCableCV: it selects TWorldcompactBatched and sets
    neither key, which is legal.

    Corrected 2026-09-26 (R2 fix, finding M6): used ``default_driver_context()``,
    which now raises ``LookupError`` -- three independent solver-tier plugins
    (cardiaccore, cardiacfoam, opencarp) are installed side by side, so there
    is no unambiguous default any more. Uses this module's own explicit
    ``_CTX`` instead, exactly like every other test here.
    """
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(
        _native_tutorials_root(), _CABLE_1D_CV_CONVERGENCE_RELPATH, cases_root,
    )
    report = strict_plan(
        "cable1DCVConvergence", driver_context=_CTX, overrides={"cases_root": str(cases_root)},
    ).to_json()
    errors = [
        d for d in report["run_document"]["validation"].get("diagnostics", [])
        if d.get("level") == "error"
    ]
    assert errors == [], f"unexpected validation errors: {errors}"


def test_electromechanics_is_advertised_as_not_working_while_it_is_not(tmp_path: Path):
    """Keep the agent-facing warning and reality in sync.

    Electromechanics is a deliberately deferred gap: the EM entry lays its
    dicts out per region (constant/electro/electroProperties) while the
    planner looks for constant/electroProperties, so it fails strict
    planning. Agents were finding that failure and trying to "fix" it.

    This asserts both halves. If EM is ever made to work, this test fails --
    which is the point: the display summary and AGENT_GUIDE warning must be
    removed in the same change, not left behind telling agents to stay away
    from something that now works.

    Corrected 2026-09-26 (R2 fix, finding M6): used ``default_driver_context()``;
    see the same correction on
    ``test_batched_ionic_model_does_not_require_optional_batched_keys`` above.
    """
    from omnidriver.cardiacfoam.tutorials.display import TUTORIALS

    entry = "manufacturedMonodomainTotalLagrangianEM"
    cases_root = tmp_path / "cases"
    _stage_case_dictionaries(_native_tutorials_root(), _MANUFACTURED_EM_RELPATH, cases_root)

    report = strict_plan(
        entry, driver_context=_CTX, overrides={"cases_root": str(cases_root)},
    ).to_json()
    errors = [
        d for d in report["run_document"]["validation"].get("diagnostics", [])
        if d.get("level") == "error"
    ]
    assert errors, (
        f"{entry} now plans cleanly. Electromechanics apparently works: drop "
        "the NOT CURRENTLY WORKING warning from tutorials/display.py and the "
        "electromechanics note from AGENT_GUIDE.md, then delete this test."
    )

    display = next(d for d in TUTORIALS if d.id == entry)
    haystack = f"{display.title} {display.summary}".lower()
    assert "not currently working" in haystack, (
        f"{entry} fails strict planning but its display does not say so; an "
        "agent will pick it and then try to repair the planner."
    )


def test_absent_stimulus_block_is_not_invented_from_defaults():
    """A case with no stimulus must not come back paced.

    stimulusIO.C:149-155 returns a no-op protocol when a case has no
    singleCellStimulus sub-dict at all; the FatalError at :159-176 only
    guards a block that exists and is incomplete. So "no stimulus" is legal.

    The catalog marked the whole family required whenever
    myocardiumSolver==singleCellSolver, and the builder satisfies a
    required-but-absent key by writing its typical_value -- so dropping the
    block yielded stim_amplitude 60 and nstim1 3, turning a quiescent run
    into a paced one.

    Corrected 2026-09-26 (R2 fix, finding M6): read the committed
    electroProperties through ``core.specs.paths.repo_root_default()``, this
    checkout's own root -- which has no ``tutorials/`` matching cardiacFoam's
    layout in a standalone install, and never did once the packages split.
    Reads directly from the (read-only) native tutorials tree instead, the
    same as every other test in this module.
    """
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
