"""Every core module must import from a real wheel, not just an editable install.

core/specs/paths.py::repo_root_default() walks up looking for a development
checkout and raises when it finds none. capability_seams.py called it at module
scope, so `import omnidriver.core.capability_seams` raised RuntimeError from
site-packages -- invisible to every editable install and to all of CI, while
release.yml built and published exactly that wheel.

Slow (builds a wheel into a throwaway venv). Marked so it can be deselected
locally with -m 'not slow'; CI runs it.
"""
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
import importlib, pkgutil, sys
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

# Importability is not the whole contract: a module can import fine and then
# point at a data file the wheel never shipped. RUN_CASE_SCRIPT_RELPATH is
# exactly that -- it resolves relative to the installed package, so it is
# correct in a checkout and wrong in an install unless run_case.sh is declared
# in [tool.setuptools.package-data]. That declaration was missing, and nothing
# here noticed, because this test only ever imported.
from omnidriver.core.runtime.generic_case import RUN_CASE_SCRIPT_RELPATH
if not RUN_CASE_SCRIPT_RELPATH.is_file():
    print(f"bundled data file missing from the wheel: {RUN_CASE_SCRIPT_RELPATH}")
    sys.exit(1)
print("bundled data files present")

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
        "from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog\\n"
        "from omnidriver.core.plugin_profile import PluginProfile\\n\\n"
        "class WheelNeutralPlugin:\\n"
        "    plugin_name = 'wheel-neutral'\\n"
        "    plugin_id = 'org.omnidriver.wheel-neutral'\\n"
        "    plugin_version = '1'\\n"
        "    plugin_api_version = '2'\\n"
        "    def get_profile(self):\\n"
        "        return PluginProfile(Path(__file__), self.plugin_id, self.plugin_api_version, (), None, {})\\n"
        "    def get_dict_entries(self): return ()\\n"
        "    def get_dictionary_catalog(self): return DictionaryCatalog({})\\n"
        "    def get_dict_groups(self): return {}\\n"
        "    def get_capabilities(self): return {}\\n"
        "    def get_tutorial_catalog(self): return {'registered_tutorials': (), 'spec_factories': {}}\\n"
        "    def get_tutorial_displays(self): return ()\\n"
        "    def validate_configuration(self, spec): return ()\\n"
        "    def validate_run_semantics(self, context): return ()\\n"
        "    def predict_data_artifacts(self, case_root, spec): return ()\\n"
        "    def get_solver_commands(self): return frozenset()\\n"
        "    def get_auxiliary_commands(self): return frozenset()\\n"
        "    def get_utility_manifests(self): return {}\\n"
        "    def get_utility_roots(self): return ()\\n"
        "    def resolve_case_models(self, case_root): return {}\\n"
        "    def get_samplable_fields(self, resolved): return {}\\n"
        "    def get_override_schema(self, tutorial_name, make_spec_info): return {}\\n"
        "    def get_run_document_config_schema(self): return {'type': 'object', 'additionalProperties': True}\\n"
        "    def get_dict_entry_catalog(self): return {}\\n"
        "    def get_solve_step_commands(self): return frozenset()\\n"
        "    def get_telemetry_source_globs(self, command): return ()\\n"
        "    def get_extra_provenance_paths(self, case_root): return ()\\n"
        "    def get_artifact_value_reader(self, artifact_format): return None\\n\\n"
        "    def get_selected_start_time(self, case_root, resolved_case):\\n"
        "        return '0'\\n\\n"
        "    def get_environment_diagnostics(self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None):\\n"
        "        return ()\\n\\n"
        "    def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None):\\n"
        "        return dict(os.environ)\\n"
    )
    case_root = root / "case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "constant").mkdir()
    control_dict = case_root / "system" / "controlDict"
    control_dict.write_text("value 1;\\n")
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
        "createdAt": "", "lastModified": "", "status": "planned", "config": {},
        "resolvedEntry": None, "workflowDag": dag, "workflowState": initial.to_json(),
        "launch": {"caseRoot": str(case_root), "outputDir": "output"},
        "expectedArtifacts": [], "validation": {},
        "terminalStatusValues": ["completed", "failed"],
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
    control_dict.write_text("value 2;\\n")
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


@pytest.mark.slow
@skip_without_repo
def test_every_core_module_imports_from_a_wheel(tmp_path) -> None:
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    python = env_dir / "bin" / "python"

    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "build"],
        check=True, capture_output=True,
    )
    # setuptools keeps a build/lib cache in the package directory and reuses
    # it, so a module deleted or MOVED since the last build is still packaged
    # from that cache. That is not hypothetical: after Phase 2 Task 2 moved
    # scripts/_rtst_scanner.py to omnidriver-cardiacfoam, a stale build/lib
    # put the old file back into the wheel and failed this test against a
    # module the source tree no longer contains. The same staleness can fail
    # in the other direction and pass a wheel that is missing something.
    # build/ is gitignored, so nothing else cleans it.
    shutil.rmtree(_REPO_ROOT / "packages" / "omnidriver" / "build", ignore_errors=True)
    subprocess.run(
        [str(python), "-m", "build", "--wheel",
         str(_REPO_ROOT / "packages" / "omnidriver"), "-o", str(tmp_path / "dist")],
        check=True, capture_output=True,
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", f"{wheel}[post]"],
        check=True, capture_output=True,
    )

    # cwd must not be the repo: it would put the source tree back on sys.path
    # and re-hide exactly what this test exists to catch.
    result = subprocess.run(
        [str(python), "-c", _WALK],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
