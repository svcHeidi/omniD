"""Command-boundary security tests for RunDocument execution."""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.workflow import validate_workflow_commands
from omnidriver.core.runtime.workflow_runner import (
    _resolve_case_cwd,
    _resolve_command,
)
from plugins.minimal_plugin import MinimalTestPlugin


def _make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\necho shadow\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class TestValidateWorkflowCommands(unittest.TestCase):
    def setUp(self) -> None:
        # The allowlist is sourced from the active plugin context. These
        # cases exercise the generic command-boundary mechanism itself
        # (CORE_NEUTRAL_COMMANDS / CASE_SCRIPT_COMMANDS short-circuit before
        # plugin_commands is even read), so a generic, non-cardiac context
        # is sufficient and keeps this file plugin-agnostic. The two cases
        # that genuinely assert cardiac-authorized commands moved to
        # omnidriver-cardiacfoam's tests/test_workflow_command_security.py.
        self.context = driver_context(
            MinimalTestPlugin(solver_commands={"gmsh", "gmshToFoam", "checkMesh"}),
            source="test:commands",
        )

    def test_gmsh_is_allowed(self) -> None:
        # Tet-mesh sweep workflows (mesh_family="tet") run gmsh/gmshToFoam/
        # checkMesh as explicit workflow steps; the allowlist must be static
        # (not gated on whether the caller's shell happens to have OpenFOAM
        # sourced), so these are named directly, same as blockMesh.
        dag = {"steps": [{"id": "s", "command": "gmsh"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_gmsh_to_foam_is_allowed(self) -> None:
        dag = {"steps": [{"id": "s", "command": "gmshToFoam"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_check_mesh_is_allowed(self) -> None:
        dag = {"steps": [{"id": "s", "command": "checkMesh"}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_mpirun_is_allowed(self) -> None:
        # run_in_parallel=True wraps the solve step as
        # `mpirun -np <N> <solver> -parallel`. mpirun itself is core-neutral,
        # but since 2026-09-20 the program it wraps is checked against the
        # same allowlist as a bare step command (test_mpirun_wrapping_an_
        # unauthorized_program_is_rejected below covers the negative case),
        # so the wrapped name here must be one this context actually
        # authorizes -- `checkMesh`, already declared in setUp.
        dag = {"steps": [{"id": "s", "command": "mpirun", "args": ["-np", "6", "checkMesh", "-parallel"]}]}
        self.assertEqual(validate_workflow_commands(dag, driver_context=self.context), ())

    def test_mpirun_wrapping_an_unauthorized_program_is_rejected(self) -> None:
        # Corrected 2026-09-20: this case used to assert the opposite --
        # that an mpirun-wrapped, unauthorized program was silently accepted
        # because only the bare `mpirun` command was allowlist-checked. That
        # was the hole; see workflow._is_authorized and
        # test_command_authorization.py::test_mpi_wrapped_payload_is_authorized.
        dag = {"steps": [{"id": "s", "command": "mpirun", "args": ["-np", "6", "cardiacFoam", "-parallel"]}]}
        codes = {d.code for d in validate_workflow_commands(dag, driver_context=self.context)}
        self.assertIn("unauthorized_mpi_payload", codes)

    def test_unknown_command_is_rejected(self) -> None:
        dag = {"steps": [{"id": "s", "command": "rm"}]}
        codes = {d.code for d in validate_workflow_commands(dag, driver_context=self.context)}
        self.assertIn("unknown_workflow_command", codes)

    def test_empty_command_is_rejected(self) -> None:
        dag = {"steps": [{"id": "s", "command": ""}]}
        codes = {d.code for d in validate_workflow_commands(dag, driver_context=self.context)}
        self.assertIn("workflow_step_without_command", codes)

    def test_explicit_relative_non_case_script_is_rejected(self) -> None:
        dag = {"steps": [{"id": "s", "command": "./notAllrun"}]}
        codes = {d.code for d in validate_workflow_commands(dag, driver_context=self.context)}
        self.assertIn("unknown_workflow_command", codes)

    def test_absolute_path_is_rejected(self) -> None:
        dag = {"steps": [{"id": "s", "command": "/usr/bin/checkMesh"}]}
        codes = {d.code for d in validate_workflow_commands(dag, driver_context=self.context)}
        self.assertIn("unknown_workflow_command", codes)

    def test_none_dag_is_empty(self) -> None:
        self.assertEqual(validate_workflow_commands(None, driver_context=self.context), ())


class TestResolveCommandShadowing(unittest.TestCase):
    def setUp(self) -> None:
        self.context = driver_context(
            MinimalTestPlugin(entrypoint="run-test-case"), source="test:commands",
        )

    def test_bare_binary_name_is_never_resolved_to_case_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cwd = Path(temp)
            _make_executable(cwd / "cardiacFoam")
            self.assertEqual(_resolve_command("cardiacFoam", cwd), "cardiacFoam")

    def test_case_script_falls_through_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(
                _resolve_command("Allrun", Path(temp), self.context), "Allrun"
            )

    def test_explicit_relative_path_passes_through(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(_resolve_command("./Allrun", Path(temp)), "./Allrun")

    def test_absolute_path_passes_through(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(_resolve_command("/usr/bin/env", Path(temp)), "/usr/bin/env")


class TestResolveCaseCwdContainment(unittest.TestCase):
    def test_symlinked_cwd_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "case"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.mkdir()
            (root / "evil").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                _resolve_case_cwd(root, "evil")

    def test_in_tree_cwd_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "case"
            (root / "sub").mkdir(parents=True)
            resolved = _resolve_case_cwd(root, "sub")
            self.assertEqual(resolved.name, "sub")


if __name__ == "__main__":
    unittest.main()
