#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_environment_preflight_composition
#
# Description
#     Final whole-branch review, Finding 1 (2026-09-22): the composed
#     `environment_preflight.load()` must thread through
#     `get_configured_environment` (the `chain`-shape member cardiacFoam's
#     real backend/library-selection logic, `configure_runtime_environment`,
#     answers), not just the `single`-shape `get_loaded_environment`. Before
#     the fix, `cli.py`'s only two run/step call sites -- both `.load()`
#     only -- never reached that logic at all. See
#     `plugin_capabilities.py`'s `_EnvironmentPreflightAdapter.load()`
#     docstring for the full trace.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Proves `.load()` on an `[env, cardiacfoam]` stack also configures.

The assertion strategy: derive the build-manifest path from `FOAM_USER_LIBBIN`
(see `configure_runtime_environment`'s fallback for `_MANIFEST_ENV`) instead
of setting `DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST` directly, so the resolved
manifest path is *output* of `configure_runtime_environment`, absent from the
merely-sourced environment `get_loaded_environment` alone would return. If
`.load()` stopped at sourcing (the bug), that key would never appear.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.runtime_profile import configure_runtime_environment
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_REQUIRED_LIBRARIES = (
    "cardiacFoam",
    "libelectroModels",
    "libionicModels",
    "libgenericWriter",
    "libactiveTensionModels",
    "libphysicsModel",
)


def _write_valid_lightweight_install(tmp_path: Path) -> Path:
    """A fake, but manifest-valid, cardiacFoam install under `tmp_path`.

    Mirrors `test_build_manifest_contract.py`'s `complete_manifest` fixture
    (same backend, same required/common libraries), except the manifest path
    is left to be *derived* from `FOAM_USER_LIBBIN` rather than declared
    directly, so its resolution is observable proof that
    `configure_runtime_environment` ran.
    """
    artifacts = []
    for name in _REQUIRED_LIBRARIES:
        path = tmp_path / name
        path.write_bytes(f"fake-{name}".encode())
        if name == "cardiacFoam":
            path.chmod(0o755)
        artifacts.append({
            "name": name,
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    payload = {
        "schema_version": 1,
        "plugin": "org.cardiacfoam",
        "backend": "lightweight",
        "openfoam": {"root": str(tmp_path)},
        "solids4foam": {"root": None},
        "linked_libraries": ["libphysicsModel.dylib"],
        "artifacts": artifacts,
    }
    manifest_path = tmp_path / "cardiacFoam.build.json"
    manifest_path.write_text(json.dumps(payload))
    return manifest_path


def _configured_env(tmp_path: Path) -> dict[str, str]:
    """The env `configure_runtime_environment` sees, matching the fixture."""
    return {
        "DRIVERFOAM_CARDIACFOAM_BACKEND": "lightweight",
        "WM_PROJECT_DIR": str(tmp_path),
        "FOAM_USER_LIBBIN": str(tmp_path),
        "PATH": str(tmp_path),
    }


def test_configure_runtime_environment_derives_the_manifest_path_from_foam_user_libbin(tmp_path):
    """Sanity check on the fixture itself, isolated from composition/sourcing:
    `configure_runtime_environment` alone must succeed and must add
    `DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST`, not merely leave it unset."""
    manifest_path = _write_valid_lightweight_install(tmp_path)

    configured, error = configure_runtime_environment(_configured_env(tmp_path))

    assert error is None
    assert configured["DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST"] == str(manifest_path)


def test_composed_load_threads_the_sourced_environment_through_configure(tmp_path, monkeypatch):
    """The real regression test: an `[env, cardiacfoam]` composed stack's
    `environment_preflight.load(...)` must return an environment carrying
    `configure_runtime_environment`'s output, not just the sourced one.
    """
    manifest_path = _write_valid_lightweight_install(tmp_path)

    # A no-op bashrc: `get_loaded_environment` must still run bash sourcing
    # (that is the `single`-shape half of `.load()`'s contract), but nothing
    # about backend selection should depend on OpenFOAM actually being
    # installed on this machine.
    bashrc = tmp_path / "bashrc"
    bashrc.write_text("# intentionally empty -- no OpenFOAM install required\n")

    system_path = os.environ.get("PATH", "")
    for key, value in _configured_env(tmp_path).items():
        if key == "PATH":
            # Keep bash itself resolvable while still resolving our fake
            # `cardiacFoam` executable first.
            monkeypatch.setenv("PATH", f"{value}{os.pathsep}{system_path}")
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("DRIVERFOAM_RUNTIME_CONFIG", raising=False)
    monkeypatch.delenv("DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST", raising=False)

    ctx = _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(),
        source="test:environment_preflight_composition",
    )

    loaded = ctx.capabilities.environment_preflight.load(
        environment_source=str(bashrc), driver_context=ctx,
    )

    # Absent from what mere sourcing produces (bash only re-exports what was
    # already in the process environment); present only because `.load()`
    # also ran the chain-composed `get_configured_environment`, which is
    # `CardiacFoamPlugin`'s real `configure_runtime_environment` call.
    assert loaded.get("DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST") == str(manifest_path)
    assert loaded.get("DRIVERFOAM_CARDIACFOAM_BACKEND") == "lightweight"
