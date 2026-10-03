"""Tests for the RunDocument execution adapter."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from unittest import mock

from omnidriver.core.planning_types import StrictDiagnostic
from omnidriver.core.runtime.run_document_exec import (
    build_execution_inputs,
    load_run_document,
)
from omnidriver.core.runtime.run_model import RunDocument
from omnidriver.core.plugin_interface import driver_context
from plugins.toy import ToyProvider

# This test declares the one case-script spelling it consumes.  Its executor
# diagnostics do not need dictionary syntax or another environment convention.
_CTX = driver_context(ToyProvider(entrypoint="run-test-case"), source="test:run-document")


def _make_runnable_case(root: Path) -> Path:
    """Create a case with this test's explicitly declared entrypoint."""
    case = root / "case"
    case.mkdir()
    (case / "run-test-case").write_text("#!/bin/sh\nexit 0\n")
    return case


def _minimal_doc(**overrides) -> RunDocument:
    base = dict(
        id="d1",
        name="doc-one",
        status="planned",
        launch={"caseRoot": "/tmp/case", "outputDir": "/tmp/case/output"},
        workflowDag={
            "schema_version": "1",
            "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
            "steps": [
                {"id": "solve", "command": "run-test-case", "args": [], "cwd": ".",
                 "depends_on": [], "produces": [], "consumes": [],
                 "retry_policy": {}, "command_display": "run-test-case"},
            ],
        },
        expectedArtifacts=[],
    )
    base.update(overrides)
    return RunDocument(**base)


class TestLoadRunDocument(unittest.TestCase):
    def test_loads_a_v3_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run.json"
            path.write_text(json.dumps(_minimal_doc().to_json()))
            doc = load_run_document(path)
            self.assertEqual(doc.name, "doc-one")
            self.assertEqual(doc.version, "3")

    def test_a_v1_or_v2_document_is_refused_not_migrated(self) -> None:
        for version in ("1", "2"):
            old = {
                "version": version,
                "id": "old",
                "name": "archived",
                "status": "planned",
            }
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "run.json"
                path.write_text(json.dumps(old))
                with self.assertRaises(ValueError):
                    load_run_document(path)

    def test_non_object_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run.json"
            path.write_text("[]")
            with self.assertRaises(ValueError):
                load_run_document(path)


class TestBuildExecutionInputsDiagnostics(unittest.TestCase):
    def test_missing_workflow_dag_is_not_executable(self) -> None:
        doc = _minimal_doc(workflowDag=None)
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("missing_workflow_dag", codes)

    def test_missing_launch_paths_are_not_executable(self) -> None:
        doc = _minimal_doc(launch={})
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("missing_case_root", codes)
        self.assertIn("missing_output_dir", codes)

    def test_unknown_command_in_dag_is_rejected(self) -> None:
        doc = _minimal_doc(workflowDag={
            "steps": [{"id": "s", "command": "rm", "args": [], "cwd": ".",
                       "depends_on": [], "produces": [], "consumes": []}],
        })
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("unknown_workflow_command", codes)

    def test_invalid_expected_artifact_is_reported(self) -> None:
        doc = _minimal_doc(expectedArtifacts=[
            {"artifact_id": "x", "path_pattern": "a/{bogus}.dat", "format": "csv_probe"},
        ])
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("invalid_expected_artifact", codes)

    def test_non_dict_launch_does_not_raise(self) -> None:
        doc = _minimal_doc(launch="not-a-dict")
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)  # must not raise
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("invalid_launch", codes)

    def test_non_iterable_expected_artifacts_does_not_raise(self) -> None:
        doc = _minimal_doc(expectedArtifacts=42)
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)  # must not raise
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("invalid_expected_artifacts", codes)

    def test_malformed_workflow_state_is_reported(self) -> None:
        doc = _minimal_doc(workflowState={"bogus": "shape"})
        inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)  # must not raise
        self.assertIsNone(inputs)
        codes = {d.code for d in diagnostics}
        self.assertIn("invalid_workflow_state", codes)

    def test_every_diagnostic_has_required_keys(self) -> None:
        # The canonical shape is core.planning_types.StrictDiagnostic
        # (level, code, message, source, field); see also
        # test_cli_run_document.py::test_every_diagnostic_carries_the_same_five_fields.
        doc = _minimal_doc(workflowDag=None, launch={})
        _inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
        expected = {"level", "code", "message", "source", "field"}
        for d in diagnostics:
            self.assertIsInstance(d, StrictDiagnostic)
            self.assertEqual({f.name for f in fields(d)}, expected)


class TestCaseRootValidation(unittest.TestCase):
    def test_nonexistent_case_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "does-not-exist"
            doc = _minimal_doc(launch={
                "caseRoot": str(missing),
                "outputDir": str(missing / "out"),
            })
            inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNone(inputs)
            codes = {d.code for d in diagnostics}
            self.assertIn("case_root_missing", codes)

    def test_canonical_paths_are_resolved_and_stored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            case = _make_runnable_case(Path(temp))
            doc = _minimal_doc(launch={
                "caseRoot": str(case),
                "outputDir": "output",  # relative -> resolves under caseRoot
            })
            inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNotNone(inputs, diagnostics)
            self.assertEqual(inputs.case_root, case.resolve())
            self.assertEqual(inputs.output_dir, (case.resolve() / "output"))


class TestAllowedRunsRoot(unittest.TestCase):
    def test_case_root_outside_allowed_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / "allowed"
            allowed.mkdir()
            case = _make_runnable_case(root)  # under root, NOT under allowed
            doc = _minimal_doc(launch={
                "caseRoot": str(case),
                "outputDir": str(case / "output"),
            })
            with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(allowed)}):
                inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNone(inputs)
            codes = {d.code for d in diagnostics}
            self.assertIn("case_root_outside_allowed_root", codes)

    def test_output_dir_outside_allowed_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / "allowed"
            allowed.mkdir()
            case = _make_runnable_case(allowed)  # case under allowed
            outside_out = root / "elsewhere"      # outputDir NOT under allowed
            doc = _minimal_doc(launch={
                "caseRoot": str(case),
                "outputDir": str(outside_out),
            })
            with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(allowed)}):
                inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNone(inputs)
            codes = {d.code for d in diagnostics}
            self.assertIn("output_dir_outside_allowed_root", codes)

    def test_both_inside_allowed_root_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            allowed = Path(temp)  # everything under the temp dir
            case = _make_runnable_case(allowed)
            doc = _minimal_doc(launch={
                "caseRoot": str(case),
                "outputDir": str(case / "output"),
            })
            with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(allowed)}):
                inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNotNone(inputs, diagnostics)

    def test_unset_allowed_root_permits_separate_output_dir(self) -> None:
        # No OMNIDRIVER_ALLOWED_RUNS_ROOT: an absolute outputDir outside the case
        # is allowed (matches resolve_spec_paths separate-results-dir layout).
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = _make_runnable_case(root)
            separate_out = root / "results"
            doc = _minimal_doc(launch={
                "caseRoot": str(case),
                "outputDir": str(separate_out),
            })
            # patch.dict (clear=False) snapshots + restores os.environ on exit,
            # so popping the var here is safe and does not disturb PATH etc.
            with mock.patch.dict(os.environ, {}):
                os.environ.pop("OMNIDRIVER_ALLOWED_RUNS_ROOT", None)
                inputs, diagnostics = build_execution_inputs(doc, driver_context=_CTX)
            self.assertIsNotNone(inputs, diagnostics)
            self.assertEqual(inputs.output_dir, separate_out.resolve())


if __name__ == "__main__":
    unittest.main()
