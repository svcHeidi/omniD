"""``sweep-plan`` must fail one case, not the whole command, on a bad axis.

Moved from omnidriver/tests/core/test_sweep_plan_contract.py (Phase 2 Task
M2): this is the one test in that module needing the real ``singleCell``
tutorial factory to prove that an unknown ionic model costs exactly one
case (a ``KeyError`` from the factory must be caught by ``sweep_plan``'s
broad per-case guard, not escape and take the whole command down). That
factory and its ionic-model vocabulary are cardiacFoam-specific, so this
test needs the full monorepo tree and stays ``@skip_without_monorepo``,
same as it was in core. The remaining three tests in that module never
touch cardiac fixture data and stayed in core.
"""

from __future__ import annotations

import json

import pytest

from conftest import skip_without_monorepo
from omnidriver.core.runtime.sweep_runner import sweep_plan
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(
    CardiacFoamPlugin(), source="test:sweep_plan_contract",
)

_SPEC = {
    "base": {
        "entry": "singleCell",
        "case_dir_name": "electrophysiologyProtocols/singleCell",
        "setup_dir_name": "setup",
    },
    "sweep": {
        "mode": "zip",
        "independent": {
            "ionic_model": ["Courtemanche", "TotallyFakeModel"],
            "tissue": ["myocyte", "myocyte"],
        },
        "dependent": [
            {"name": "caseId", "derive": "case_id_template",
             "of": ["ionic_model", "tissue"]},
            {"name": "output_dir_name", "derive": "output_dir_name_template",
             "of": ["ionic_model", "tissue"]},
        ],
    },
}


@skip_without_monorepo
def test_a_factory_failure_fails_one_case_not_the_command(tmp_path):
    """An unknown ionic model must cost exactly one case."""
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(_SPEC))

    report = sweep_plan(spec_path, output_dir=tmp_path / "out", driver_context=_CTX)

    failed = [c for c in report["cases"] if c["status"] == "failed"]
    assert len(failed) == 1, report["cases"]
    assert "TotallyFakeModel" in failed[0]["materialization_error"]
    # ...and the good case still planned.
    assert any(c["status"] != "failed" for c in report["cases"]), report["cases"]
