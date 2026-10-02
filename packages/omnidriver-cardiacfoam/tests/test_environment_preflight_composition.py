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
#     The composed `environment_preflight.load()` must thread through the
#     `chain`-shape `get_configured_environment`, not just the `single`-shape
#     `get_loaded_environment`.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Proves `.load()` on an `[env, cardiacfoam]` stack also configures: the build-manifest path is
derived from `FOAM_USER_LIBBIN` by `configure_runtime_environment`, so it is absent from a merely
sourced environment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.runtime_profile import configure_runtime_environment
from omnidriver.core.environment_connection import load_environment
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
    """A fake, manifest-valid install whose manifest path is left to be derived from `FOAM_USER_LIBBIN`."""
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
        "OMNIDRIVER_CARDIACFOAM_BACKEND": "lightweight",
        "WM_PROJECT_DIR": str(tmp_path),
        "FOAM_USER_LIBBIN": str(tmp_path),
        "PATH": str(tmp_path),
    }


def test_configure_runtime_environment_derives_the_manifest_path_from_foam_user_libbin(tmp_path):
    manifest_path = _write_valid_lightweight_install(tmp_path)

    configured, error = configure_runtime_environment(_configured_env(tmp_path))

    assert error is None
    assert configured["OMNIDRIVER_CARDIACFOAM_BUILD_MANIFEST"] == str(manifest_path)


def test_composed_load_threads_the_sourced_environment_through_configure(tmp_path, monkeypatch):
    manifest_path = _write_valid_lightweight_install(tmp_path)

    # A no-op bashrc: sourcing still runs, but backend selection must not need an installed OpenFOAM.
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
    monkeypatch.delenv("OMNIDRIVER_RUNTIME_CONFIG", raising=False)
    monkeypatch.delenv("OMNIDRIVER_CARDIACFOAM_BUILD_MANIFEST", raising=False)

    ctx = _driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(),
        source="test:environment_preflight_composition",
    )

    loaded = load_environment(ctx, str(bashrc))

    # Sourcing only re-exports the process environment; this key comes from `configure_runtime_environment`.
    assert loaded.get("OMNIDRIVER_CARDIACFOAM_BUILD_MANIFEST") == str(manifest_path)
    assert loaded.get("OMNIDRIVER_CARDIACFOAM_BACKEND") == "lightweight"
