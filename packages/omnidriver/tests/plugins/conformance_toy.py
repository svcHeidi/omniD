"""The toy conformance target: E2ERecordPlugin's toyTutorial.

The native case is written into tmp_path by the caller's test, the same way
test_sweep_run_plugin_propagation builds it, but with a second key
(``label``). A one-key document cannot show a sibling key being lost; that
is how P2 hid.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from omnidriver.conformance import ConformanceTarget

TESTS_ROOT = Path(__file__).resolve().parents[1]
TOY_PLUGIN = "plugins.e2e_record_plugin:E2ERecordPlugin"


def write_toy_native_case(cases_root: Path) -> Path:
    native = cases_root / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
    return native


def toy_conformance_target(tmp_path: Path, *, plugin: str = TOY_PLUGIN) -> ConformanceTarget:
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    return ConformanceTarget(
        plugin=plugin,
        record="toyTutorial",
        cases_root=cases_root,
        scratch_root=tmp_path / "scratch",
        base_study={},
        patch=("constant/mesh.json:cells", 7),
        untouched=("constant/mesh.json", ("label",)),
        sweep_name="number_cells",
        sweep_values=(2, 3),
        unknown_name="cell_count",
        solver_command="touch",
        environment={
            "PYTHONPATH": os.pathsep.join([str(TESTS_ROOT), os.environ.get("PYTHONPATH", "")]),
        },
    )
