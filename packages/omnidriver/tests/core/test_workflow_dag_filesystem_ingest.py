"""Tests for filesystem case workflow ownership.

Plain case folders are owned by their plugin-declared case script. Registry
discovery may find a marked folder, but Core creates no workflow DAG unless
the declared script exists.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from omnidriver.core.runtime.generic_case import make_generic_case_spec
from omnidriver.core.runtime.registry import load_tutorial_spec, resolve_entry
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from plugins.minimal_plugin import MinimalTestPlugin


class _FilesystemMarkerPlugin(MinimalTestPlugin):
    """A test-only case marker with no solver vocabulary.

    The marker is deliberately plain filesystem evidence; it carries no
    solver vocabulary.
    """

    def has_case_marker(self, case_root: Path) -> bool:
        return (
            (case_root / "metadata" / "case.txt").is_file()
            and (case_root / "inputs").is_dir()
        )

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(
            output_collection_relpath="outputs",
            case_entrypoints=("run-case",),
            case_script_commands=("run-case",),
        )

    def get_tutorial_catalog(self):
        # resolve_entry() looks up "make_generic_case_spec" in the selected
        # plugin's own tutorial catalog once has_case_marker() is True (see
        # registry.py); wire it to the same core factory the no-marker
        # branch already falls back to, so which branch runs makes no
        # behavioural difference here.
        catalog = dict(super().get_tutorial_catalog())
        catalog["make_generic_case_spec"] = make_generic_case_spec
        return catalog


_CTX = _driver_context(
    _FilesystemMarkerPlugin(entrypoint="run-case"),
    source="test:workflow_dag_filesystem_ingest",
)


class TestFilesystemCaseWorkflowOwnership(unittest.TestCase):
    """Filesystem case folders own their run definition through a declaration."""

    def _write_case_files(self, case_root: Path) -> None:
        (case_root / "inputs").mkdir(parents=True, exist_ok=True)
        (case_root / "metadata").mkdir(parents=True, exist_ok=True)
        (case_root / "metadata" / "case.txt").write_text("")

    def test_filesystem_case_with_declared_script_uses_that_script(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases_root = Path(temp_dir)
            case_root = cases_root / "myCase"
            self._write_case_files(case_root)
            (case_root / "run-case").write_text("#!/bin/sh\n")

            spec = load_tutorial_spec(
                "myCase",
                overrides={"cases_root": cases_root},
                driver_context=_CTX,)

            dag = spec.metadata.get("workflow_dag")
            self.assertEqual(
                dag,
                {"steps": [{"id": "run", "command": "run-case", "depends_on": []}]},
            )

    def test_filesystem_case_without_declared_script_has_no_workflow_dag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cases_root = Path(temp_dir)
            case_root = cases_root / "bareCase"
            self._write_case_files(case_root)

            spec = load_tutorial_spec(
                "bareCase",
                overrides={"cases_root": cases_root},
                driver_context=_CTX,)

            dag = spec.metadata.get("workflow_dag")
            self.assertIsNone(dag, "workflow_dag must be None when the declared script is absent")


if __name__ == "__main__":
    unittest.main()
