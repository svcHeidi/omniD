"""A strict plan refuses a solver the catalogue and the C++ do not list, by name, before anything
runs. The case is written inline."""
from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError, WorkflowStep
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def test_a_solver_nothing_lists_is_refused_by_name(tmp_path):
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

    with pytest.raises(TutorialRecordError) as refusal:
        strict_plan(
            TutorialRecord(
                name="missingArtifacts", native_case_relpath="missingArtifacts",
                workflow_steps=(WorkflowStep(step_id="solve", command=("cardiacFoam",)),),
            ),
            overrides={"cases_root": str(cases_root)},
            scratch_root=tmp_path / "scratch",
            driver_context=driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:strict_plan"),
        )
    message = str(refusal.value)
    assert "myocardiumSolver is 'futureSolver', not one of the values the catalogue lists" in message
