"""Cardiac adapter introspection declarations, using an explicit case root."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from omnidriver.cli import main
from omnidriver.core.introspection import describe_tutorial
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

# These payloads are the cardiac adapter's own introspection, so the context
# is supplied rather than discovered: the ambient default is ambiguous as soon
# as a second adapter is installed (future/ENVIRONMENT_CONTRACT.md §12).
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:introspection")


def _single_cell_case_root(cases_root: Path) -> Path:
    """Minimal declared-input fixture; no checkout discovery or solver run."""
    case_root = cases_root / "electrophysiologyProtocols" / "singleCell"
    for relative in (
        "constant/electroProperties",
        "constant/physicsProperties",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/decomposeParDict",
        "system/blockMeshDict",
        "Allrun",
        "README.md",
    ):
        path = case_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" if relative == "Allrun" else "// fixture\n")
    (case_root / "Allrun").chmod(0o755)
    return case_root


def _describe_single_cell(cases_root: Path) -> dict:
    _single_cell_case_root(cases_root)
    return describe_tutorial(
        "singleCell",
        overrides={"cases_root": cases_root},
        driver_context=_CTX,
    )


def test_describe_single_cell_reports_cardiac_adapter_schema(tmp_path: Path) -> None:
    payload = _describe_single_cell(tmp_path)

    assert payload["resolution"] == "registered"
    assert payload["resolved_name"] == "singleCell"
    assert "ionic_models" in payload["make_spec"]["parameters"]
    assert "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1" in {
        item["driver_path"]
        for item in payload["dict_entries"]["electroProperties"]["single_cell_stimulus"]
    }
    assert payload["spec"]["case_root"] == str(_single_cell_case_root(tmp_path))
    assert "Allrun" in payload["tutorial_contract"]["conditional_files"]
    assert "ionicModel" in payload["tutorial_contract"]["case_parameters"]
    assert "--strict" in payload["strict_launch"]["command"]


def test_describe_single_cell_exposes_cardiac_catalogs(tmp_path: Path) -> None:
    payload = _describe_single_cell(tmp_path)
    catalogs = payload["plugin_catalogs"]

    ionic = catalogs["ionic_model_catalog"]
    assert ionic["schema_version"] == "1.0"
    tnnp = ionic["ionic_models"]["TNNP"]
    for key in (
        "states", "algebraic", "recommended_exports", "compatible_tissues",
        "native_tissue_labels", "approximate_tissue_labels", "compatible_solvers",
        "species", "cardiac_region", "model_type",
    ):
        assert key in tnnp
    assert isinstance(tnnp["states"], list)
    assert catalogs["active_tension_catalog"]["schema_version"] == "1.0"


def test_cardiac_plugin_describes_an_explicit_case_folder(tmp_path: Path) -> None:
    case_root = tmp_path / "randomCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "electroProperties").write_text(
        "myocardiumSolver singleCellSolver;\n"
        "singleCellSolverCoeffs\n{\n    ionicModel BuenoOrovio;\n}\n"
    )
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")

    payload = describe_tutorial(
        "randomCase",
        overrides={"cases_root": tmp_path},
        driver_context=_CTX,
    )

    assert payload["resolution"] == "case_folder"
    assert payload["make_spec"]["callable"] == (
        "omnidriver.cardiacfoam.tutorials.generic_case.make_generic_case_spec"
    )
    assert payload["tutorial_contract"]["core_required_files"] == [
        "constant/electroProperties", "constant/physicsProperties",
    ]


def test_cardiac_profile_contract_file_order_is_declared(tmp_path: Path) -> None:
    case_root = _single_cell_case_root(tmp_path)
    for relative in ("Allclean", "runRegressionTest.sh"):
        path = case_root / relative
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)

    payload = describe_tutorial(
        "singleCell",
        overrides={"cases_root": tmp_path},
        driver_context=_CTX,
    )
    contract = payload["tutorial_contract"]
    assert contract["core_required_files"] == [
        "constant/electroProperties", "constant/physicsProperties",
    ]
    # `constant` (role `openfoam.case_directory`) now appears: it was always
    # required, but only became visible once the environment adapter (Task
    # 9) actually composes into `_CTX` instead of cardiacFoam's own profile
    # being the only one in a single-provider stack.
    assert contract["solver_required_files"] == [
        "system/controlDict", "constant", "system/fvSchemes", "system/fvSolution",
    ]
    # `Allrun` now leads: it is the environment adapter's declaration
    # (composed first, being least-specific), not cardiacFoam's own -- the
    # duplicate `Allrun` role cardiacFoam's own profile used to carry was
    # removed as part of Task 9's case-file de-duplication.
    assert contract["conditional_files"] == [
        "Allrun", "system/decomposeParDict", "system/blockMeshDict", "Allclean",
        "README.md", "runRegressionTest.sh",
    ]


def test_cli_describe_prints_cardiac_payload_for_explicit_case_root(tmp_path: Path) -> None:
    _single_cell_case_root(tmp_path)
    stream = io.StringIO()
    with redirect_stdout(stream):
        exit_code = main([
            "describe", "--plugin", "cardiacfoam",
            "--entry", "singleCell", "--cases-root", str(tmp_path),
        ])

    assert exit_code == 0
    payload = json.loads(stream.getvalue())
    assert payload["resolved_name"] == "singleCell"
    assert "strict_launch" in payload


def test_cli_describe_requires_entry_name() -> None:
    with pytest.raises(SystemExit):
        main(["describe"])
