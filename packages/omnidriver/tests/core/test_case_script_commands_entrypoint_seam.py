"""A plugin's declared openfoam.entrypoint now resolves case-locally, not
just the fixed Allrun-family names (Tier 4, entrypoint slice --
future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md). Covers the
core-side sites: workflow.py's allowlist and case_script_commands(),
workflow_runner.py's command resolution and DYLD dot-source wrapper,
provenance_inputs.py's fingerprinting mirror, and
capability_manifest.py's advertisement. The sixth site
(omnidriver-openfoam's environment_preflight._required_executables) is
covered in that package's own test tree instead -- core's suite must
never assume omnidriver-openfoam is installed (see
plugins/neutral_environment_plugin.py's own docstring for why). These
tests need no monorepo tutorials tree -- unlike
test_trust_boundary_end_to_end.py, which exercises the same invariant
for the fixed names through the full CLI but is entirely
skip_without_monorepo-gated in a standalone checkout.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.capability_manifest import build_capability_manifest
from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from omnidriver.core.runtime.provenance_inputs import _is_case_local_script
from omnidriver.core.runtime.workflow import (
    CASE_SCRIPT_COMMANDS,
    case_script_commands,
    validate_workflow_commands,
)
from omnidriver.core.runtime.workflow_runner import _argv_for_execution, _resolve_command
from plugins.neutral_environment_plugin import NeutralEnvironmentPlugin


class _ForeignEntrypointPlugin(NeutralEnvironmentPlugin):
    """Declares its entrypoint as "run.sh", not "Allrun" -- proves the seam
    is a genuine escape from the fixed name, not just a coincidence of
    every shipped plugin happening to use "Allrun" today."""

    def get_profile(self) -> PluginProfile:
        return PluginProfile(
            path=Path(__file__),
            plugin_id=self.plugin_id,
            api_version=self.plugin_api_version,
            case_files=(
                CaseFileRule(
                    path="run.sh", kind="case_script",
                    role="openfoam.entrypoint", required="conditional",
                ),
            ),
            cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                "case_profile": {"dictionaries": []},
            },
        )


def _write_executable(path: Path, content: str = "#!/bin/sh\n") -> None:
    path.write_text(content)
    path.chmod(0o755)


def test_case_script_commands_defaults_to_the_fixed_set_with_no_context() -> None:
    assert case_script_commands(None) == CASE_SCRIPT_COMMANDS


def test_shipped_plugins_advertise_only_the_fixed_set() -> None:
    """Zero behavior change for either shipped plugin: both declare their
    entrypoint as exactly "Allrun", already in CASE_SCRIPT_COMMANDS."""
    manifest = GenericOpenFOAMPlugin().get_capabilities()
    assert manifest["allowed_commands"]["case_scripts"] == sorted(CASE_SCRIPT_COMMANDS)


def test_a_foreign_plugins_declared_entrypoint_is_included(tmp_path: Path) -> None:
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")
    assert case_script_commands(ctx) == CASE_SCRIPT_COMMANDS | {"run.sh"}


def test_declared_entrypoint_resolves_case_locally(tmp_path: Path) -> None:
    """SECURITY.md: 'No command shadowing' -- extended to a plugin's own
    entrypoint name, not just the fixed Allrun-family names."""
    _write_executable(tmp_path / "run.sh")
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")

    assert _resolve_command("run.sh", tmp_path, ctx) == str(tmp_path / "run.sh")
    # Without the plugin declaring it, the same name is never treated as a
    # case script -- proving the resolution is genuinely plugin-gated, not
    # a hole that accepts any bare name with a matching case-local file.
    assert _resolve_command("run.sh", tmp_path) == "run.sh"


def test_core_neutral_commands_never_resolve_case_locally_even_with_a_foreign_context(
    tmp_path: Path,
) -> None:
    """The core invariant this whole seam must not weaken: a case directory
    still cannot shadow a trusted PATH binary, regardless of which plugin
    is active."""
    _write_executable(tmp_path / "blockMesh", "#!/bin/sh\necho SHADOW\n")
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")

    assert _resolve_command("blockMesh", tmp_path) == "blockMesh"
    assert _resolve_command("blockMesh", tmp_path, ctx) == "blockMesh"


def test_allowlist_accepts_the_declared_entrypoint_only_for_its_own_plugin() -> None:
    dag = {"steps": [{"id": "run", "command": "run.sh", "depends_on": []}]}
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")

    assert validate_workflow_commands(dag, driver_context=ctx) == ()

    diagnostics = validate_workflow_commands(dag, driver_context=None)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "unknown_workflow_command"


def test_dyld_dot_source_wrapper_applies_to_a_declared_entrypoint_too() -> None:
    """The macOS-SIP DYLD-preservation wrapper (workflow_runner._argv_for_execution)
    must recognise the declared entrypoint, not just the fixed names -- a
    partial fix here would silently lose a foreign plugin's DYLD_* env on
    macOS even after command resolution and the allowlist are both fixed."""
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")
    env = {"DYLD_LIBRARY_PATH": "/some/lib"}

    wrapped = _argv_for_execution("run.sh", "/case/run.sh", (), env, ctx)
    assert wrapped[0] == "/bin/sh", "declared entrypoint should get the DYLD wrapper"

    unwrapped = _argv_for_execution("run.sh", "/case/run.sh", (), env, None)
    assert unwrapped == ("/case/run.sh",), "without the plugin, no wrapping"


def test_provenance_fingerprinting_agrees_with_the_executor(tmp_path: Path) -> None:
    """provenance_inputs._is_case_local_script mirrors _resolve_command's own
    precondition -- if this drifts, provenance fingerprinting misclassifies
    the entrypoint script for a foreign plugin."""
    _write_executable(tmp_path / "run.sh")
    ctx = driver_context(_ForeignEntrypointPlugin(), source="test")

    local = _is_case_local_script(
        "run.sh", str(tmp_path / "run.sh"),
        resolved_cwd=tmp_path, case_root=tmp_path, driver_context=ctx,
    )
    assert local == tmp_path / "run.sh"

    local_without_plugin = _is_case_local_script(
        "run.sh", str(tmp_path / "run.sh"),
        resolved_cwd=tmp_path, case_root=tmp_path, driver_context=None,
    )
    assert local_without_plugin is None


def test_build_capability_manifest_advertises_a_custom_case_script_set() -> None:
    manifest = build_capability_manifest(case_script_commands=frozenset({"run.sh"}))
    assert manifest["allowed_commands"]["case_scripts"] == ["run.sh"]


def test_build_capability_manifest_defaults_to_the_fixed_set() -> None:
    manifest = build_capability_manifest()
    assert manifest["allowed_commands"]["case_scripts"] == sorted(CASE_SCRIPT_COMMANDS)
