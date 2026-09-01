"""Core's own artifacts must be predicted where core actually writes them.

``workflow_state.json`` and ``workflow_logs/`` are core's, not the
environment's: core owns their names, their schema and their placement, and
``execution_context.resolve_execution_context`` puts them at
``spec.output_dir / ...``. What core does *not* own is where ``output_dir``
is -- that comes from the spec's ``output_dir_name``, whose default happens
to be OpenFOAM's ``postProcessing``.

``artifacts._core_generic_artifacts`` used to predict the literal
``postProcessing/workflow_state.json`` regardless. With the default they
agree, so nothing noticed. Override ``output_dir_name`` and core writes
``results/workflow_state.json`` while still promising
``postProcessing/workflow_state.json`` -- artifact reconciliation then looks
for a file that was never going to be there and reports core's own guaranteed
artifact missing.

The bug is a coincidence between two independent constants, which is exactly
what a test using only the default value cannot see. So these assert the
CONTRAST: the prediction must move when the output dir moves.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.runtime.artifacts import _core_generic_artifacts
from omnidriver.core.runtime.execution_context import resolve_execution_context
from omnidriver.core.runtime.generic_case import make_spec


def _spec(root: Path, **kwargs):
    (root / "myCase").mkdir(parents=True, exist_ok=True)
    return make_spec(tutorials_root=root, case_dir_name="myCase", **kwargs)


@pytest.mark.parametrize("output_dir_name", [None, "results", "driverOutput"])
def test_the_predicted_state_path_is_where_core_writes_it(tmp_path, output_dir_name) -> None:
    kwargs = {} if output_dir_name is None else {"output_dir_name": output_dir_name}
    spec = _spec(tmp_path, **kwargs)

    written = resolve_execution_context(spec).workflow_state_path
    predicted = next(
        a for a in _core_generic_artifacts(spec) if a.artifact_id == "core.workflow_state"
    )

    # path_pattern is case-relative (models.DataArtifact).
    assert Path(spec.case_root) / predicted.path_pattern == written


def test_a_non_default_output_dir_actually_moves_the_prediction(tmp_path) -> None:
    """Guards the contrast, not just the agreement.

    Without this, an implementation that hardcodes 'postProcessing' passes the
    default case above and fails nothing.
    """
    default = _core_generic_artifacts(_spec(tmp_path / "a"))
    moved = _core_generic_artifacts(_spec(tmp_path / "b", output_dir_name="results"))

    assert [a.path_pattern for a in default] == [
        "postProcessing/workflow_state.json",
        "postProcessing/workflow_logs",
    ]
    assert [a.path_pattern for a in moved] == [
        "results/workflow_state.json",
        "results/workflow_logs",
    ]
