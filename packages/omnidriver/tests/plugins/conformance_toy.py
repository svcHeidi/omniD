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

import json as _json

from omnidriver.core.case_write import RenderedFile, _digest_bytes

from plugins.e2e_record_plugin import E2ERecordPlugin, _FORMAT, _deep_set

REPLACING_PLUGIN = "plugins.conformance_toy:ReplacingRendererPlugin"


class ReplacingRendererPlugin(E2ERecordPlugin):
    """Truthful about exists_before, but writes a document holding only the
    patched keys. case_transaction accepts it; only C4 can catch it."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        rendered = []
        for target in resolved.targets:
            path = Path(snapshot_root) / target["document"]
            exists_before = path.exists()
            content_obj: dict = {}
            _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            rendered.append(RenderedFile(
                path=target["document"], content=(_json.dumps(content_obj) + "\n").encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)


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
