"""cardiacFOAM #59's ECG runs in 3D only: a 1D or 2D run removes ``ecgDomains``, so neither a record's step nor the
predictor may expect an ECG file from it. ``fixtures/local_includes/electroProperties`` is verbatim from #59's
monodomainPseudoECG."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.artifacts_predictor import predict_cardiac_artifacts
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.mutators import remove_foam_dict

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:ecg_is_3d_only")
_ELECTRO = Path(__file__).parent / "fixtures" / "local_includes" / "electroProperties"


def _is_ecg(path: str) -> bool:
    return "ECG" in path or path.endswith("pseudoECG.dat")


@pytest.mark.parametrize("record_name", ["manufacturedMonodomainPseudoECG", "manufacturedEikonalECG"])
def test_no_step_declares_an_ecg_file(record_name):
    record = _CTX.stack.call("get_tutorial_records")[record_name]
    assert not [path for step in record.workflow_steps for path in step.produces if _is_ecg(path)]


def test_the_ecg_is_predicted_only_while_the_case_has_it(tmp_path):
    (tmp_path / "constant").mkdir()
    properties = tmp_path / "constant" / "electroProperties"
    shutil.copy(_ELECTRO, properties)
    assert [a.path_pattern for a in predict_cardiac_artifacts(tmp_path, None) if _is_ecg(a.path_pattern)] == [
        "postProcessing/pseudoECG.dat",
    ]
    remove_foam_dict(properties, "ecgDomains", scope=("monodomainSolverCoeffs",))
    assert not [a.path_pattern for a in predict_cardiac_artifacts(tmp_path, None) if _is_ecg(a.path_pattern)]
