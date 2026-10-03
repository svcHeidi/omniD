"""Every core module must import from a real wheel, not just an editable install."""
from __future__ import annotations

import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from conftest import skip_without_repo

_REPO_ROOT = Path(__file__).resolve().parents[4]

_WALK = """
import importlib, pkgutil, sys, subprocess
import omnidriver
bad = []
for module in pkgutil.walk_packages(omnidriver.__path__, "omnidriver."):
    if "conftest" in module.name:
        continue
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        bad.append(f"{module.name}: {type(exc).__name__}: {exc}")

# Modules known to fail from a wheel for a reason tracked elsewhere. This set
# may only SHRINK: an entry that stops matching fails the test, so it cannot
# rot into a lie the way a silently-broad assertion would.
KNOWN_UNIMPORTABLE = set()

unexpected = [line for line in bad if line.split(":")[0] not in KNOWN_UNIMPORTABLE]
stale = KNOWN_UNIMPORTABLE - {line.split(":")[0] for line in bad}
if stale:
    print("KNOWN_UNIMPORTABLE entries that now import fine -- delete them: "
          + ", ".join(sorted(stale)))
    sys.exit(1)
if unexpected:
    print("\\n".join(unexpected))
    sys.exit(1)
print("all modules imported")

help_result = subprocess.run(
    [sys.executable, "-m", "omnidriver", "--help"],
    capture_output=True,
    text=True,
)
if help_result.returncode:
    print(help_result.stdout + help_result.stderr)
    sys.exit(help_result.returncode)
print("core-only CLI help works")

# Core has no environment adapter.  Selecting one is an installation concern,
# not a compatibility fallback supplied by the Core wheel.
try:
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
except ModuleNotFoundError:
    pass
else:
    print("Core wheel unexpectedly provides the OpenFOAM environment adapter")
    sys.exit(1)

# A RunDocument can carry a previous workflow state instead of relying on an
# adjacent workflow_state.json. That state must be checked as resume evidence,
# not treated as an unconditional completed result. This is deliberately a
# core-only, shell-only workflow: it exercises the public CLI from the wheel
# without requiring an OpenFOAM or cardiacFOAM installation.
import json, os, subprocess, tempfile
from pathlib import Path
from omnidriver.core.runtime.workflow_state import initial_workflow_state

with tempfile.TemporaryDirectory() as raw:
    root = Path(raw)
    plugin_path = Path.cwd() / "wheel_neutral_plugin.py"
    plugin_path.write_text(
        "import os\\n"
        "from pathlib import Path\\n"
        "from omnidriver.core.plugin_interface import CaseRuntimeConventions\\n"
        "from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile\\n\\n"
        "class WheelNeutralPlugin:\\n"
        "    plugin_name = 'wheel-neutral'\\n"
        "    plugin_id = 'org.omnidriver.wheel-neutral'\\n"
        "    plugin_version = '1'\\n"
        "    plugin_api_version = '3'\\n"
        "    def get_profile(self):\\n"
        "        return PluginProfile(\\n"
        "            Path(__file__), self.plugin_id, self.plugin_api_version,\\n"
        "            (CaseFileRule('inputs/config.txt', 'text', 'x-test.input', 'conditional'),),\\n"
        "            None, {},\\n"
        "        )\\n"
        "    def get_case_runtime_conventions(self):\\n"
        "        return CaseRuntimeConventions(case_entrypoints=('Allrun',), case_script_commands=('Allrun',))\\n\\n"
        "    def get_input_roots(self, case_root, resolved_case, *, conventions):\\n"
        "        return ('0',)\\n\\n"
        "    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):\\n"
        "        return ()\\n\\n"
        "    def get_loaded_environment(self, *, environment_source=None, driver_context=None):\\n"
        "        return dict(os.environ)\\n"
    )
    case_root = root / "case"
    (case_root / "inputs").mkdir(parents=True)
    (case_root / "constant").mkdir()
    config_file = case_root / "inputs" / "config.txt"
    config_file.write_text("value 1;\\n")
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\\nexit 0\\n")
    os.chmod(allrun, 0o755)
    dag = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [{
            "id": "run", "command": "Allrun", "args": [], "cwd": ".",
            "depends_on": [], "produces": [], "consumes": [],
            "retry_policy": {"max_attempts": 1}, "command_display": "Allrun",
        }],
    }
    initial = initial_workflow_state(dag)
    document = {
        "version": "3", "id": "wheel-resume", "name": "wheel-resume",
        "status": "planned",
        "resolvedEntry": None, "workflowDag": dag, "workflowState": initial.to_json(),
        "launch": {"caseRoot": str(case_root), "outputDir": "output"},
        "expectedArtifacts": [], "validation": {},
    }
    document_path = root / "run.json"
    document_path.write_text(json.dumps(document))
    command = [sys.executable, "-m", "omnidriver", "run",
               "--plugin", "wheel_neutral_plugin:WheelNeutralPlugin",
               "--run-document", str(document_path)]
    first = subprocess.run(command, capture_output=True, text=True)
    if first.returncode:
        print(first.stdout + first.stderr)
        sys.exit(first.returncode)
    checkpoint = Path(json.loads(first.stdout)["workflow_state_path"])
    document["workflowState"] = json.loads(checkpoint.read_text())
    document_path.write_text(json.dumps(document))
    checkpoint.unlink()
    config_file.write_text("value 2;\\n")
    resumed = subprocess.run(command, capture_output=True, text=True)
    if resumed.returncode != 1:
        print(resumed.stdout + resumed.stderr)
        sys.exit(1)
    diagnostics = json.loads(resumed.stdout).get("diagnostics", [])
    if "workflow_state_resume_rejected" not in {item.get("code") for item in diagnostics}:
        print(resumed.stdout + resumed.stderr)
        sys.exit(1)
print("embedded RunDocument resume evidence rejected after input drift")
"""


def _fail_environment(what: str, detail: str) -> None:
    """Fail loudly, naming the failure as the harness (not the wheel) and printing what the subprocess said."""
    pytest.fail(
        f"test environment could not be built ({what}); this is an "
        f"infrastructure failure, not a defect in the wheel:\n{detail}"
    )


def _create_environment(env_dir: Path) -> Path:
    """Create the throwaway venv this test builds and installs the wheel into."""
    try:
        venv.create(env_dir, with_pip=True, symlinks=True)
    except subprocess.CalledProcessError as error:
        _fail_environment(
            "venv.create",
            f"{error}\n{error.stdout or ''}{error.stderr or ''}",
        )
    return env_dir / "bin" / "python"


def _run_environment_step(command: list[str], what: str) -> None:
    """Run one environment-construction step, reporting its output on failure."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        _fail_environment(what, result.stdout + result.stderr)


@pytest.mark.slow
@skip_without_repo
def test_every_core_module_imports_from_a_wheel(tmp_path) -> None:
    python = _create_environment(tmp_path / "venv")

    _run_environment_step(
        [str(python), "-m", "pip", "install", "-q", "build"],
        "pip install build",
    )
    # setuptools keeps a build/lib cache in the package directory and reuses
    # it, so a module deleted or moved since the last build can still be
    # packaged from that stale cache (in either direction); build/ is
    # gitignored, so nothing else cleans it.
    shutil.rmtree(_REPO_ROOT / "packages" / "omnidriver" / "build", ignore_errors=True)
    _run_environment_step(
        [str(python), "-m", "build", "--wheel",
         str(_REPO_ROOT / "packages" / "omnidriver"), "-o", str(tmp_path / "dist")],
        "python -m build",
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    _run_environment_step(
        [str(python), "-m", "pip", "install", "-q", f"{wheel}[post]"],
        "pip install the built wheel",
    )

    # cwd must not be the repo: it would put the source tree back on sys.path
    # and re-hide exactly what this test exists to catch.
    result = subprocess.run(
        [str(python), "-c", _WALK],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
