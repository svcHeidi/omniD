"""OpenFOAM input-evidence behavior used by Core resume validation."""

from __future__ import annotations

import json
import sys

import pytest

from omnidriver.core.runtime.resume import validate_resume
from omnidriver.core.runtime.workflow_runner import run_workflow_step
from omnidriver.core.runtime.workflow_state import initial_workflow_state, workflow_state_from_json
from omnidriver.openfoam.environment import openfoam_environment_context


def _completed(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text("startTime 0;\n")
    dag = {
        "steps": [{
            "id": "solve",
            "command": sys.executable,
            "args": ["-c", "from pathlib import Path; Path('result.txt').write_text('done')"],
            "cwd": ".",
            "depends_on": [],
        }],
    }
    output = tmp_path / "output"
    result = run_workflow_step(
        dag,
        initial_workflow_state(dag),
        "solve",
        case_root=tmp_path,
        log_dir=output / "optional-logs",
        state_path=output / "optional-state.json",
        env={},
        driver_context=openfoam_environment_context(),
    )
    return dag, output, result.state


def test_optional_include_absence_resumes_but_appearance_refuses(tmp_path) -> None:
    dag, output, _state = _completed(tmp_path)
    optional = tmp_path / "runtime" / "optional.cfg"
    control_dict = tmp_path / "system" / "controlDict"
    control_dict.write_text(f'#includeIfPresent "{optional}"\nstartTime 0;\n')
    # Recreate the checkpoint after adding the optional declaration, while it
    # remains absent. The absence witness is complete resume evidence.
    result = run_workflow_step(
        dag,
        initial_workflow_state(dag),
        "solve",
        case_root=tmp_path,
        log_dir=output / "optional-logs",
        state_path=output / "optional-state.json",
        env={},
        driver_context=openfoam_environment_context(),
    )
    saved = workflow_state_from_json(
        json.loads((output / "optional-state.json").read_text())
    )
    assert saved == result.state
    validate_resume(
        saved,
        dag,
        case_root=tmp_path,
        driver_context=openfoam_environment_context(),
        env={},
    )
    optional.parent.mkdir()
    optional.write_text("value 2;\n")
    with pytest.raises(ValueError, match="input evidence changed"):
        validate_resume(
            saved,
            dag,
            case_root=tmp_path,
            driver_context=openfoam_environment_context(),
            env={},
        )
