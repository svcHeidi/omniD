from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class OpenFOAMEnvironment:
    env: dict[str, str]
    bashrc: str | None = None
    error: str | None = None


def _parse_exported_environment(payload: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in payload.splitlines():
        if not line.startswith("declare -x "):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) < 3:
            continue
        assignment = parts[2]
        if "=" in assignment:
            key, value = assignment.split("=", 1)
        else:
            key, value = assignment, ""
        env[key] = value
    return env


RUNTIME_CONFIG_ENV = "OMNIDRIVER_RUNTIME_CONFIG"


def configured_openfoam_bashrc(env: Mapping[str, str]) -> str | None:
    """The ``openfoam.bashrc`` of the host runtime file ``OMNIDRIVER_RUNTIME_CONFIG``
    names, or ``None`` when no file is declared or it names none."""
    config_name = env.get(RUNTIME_CONFIG_ENV)
    if not config_name:
        return None
    config_path = Path(os.path.expandvars(config_name)).expanduser().resolve()
    if not config_path.is_file():
        return None
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    openfoam = payload.get("openfoam") if isinstance(payload, dict) else None
    value = openfoam.get("bashrc") if isinstance(openfoam, dict) else None
    return str(value) if value else None


def supplied_openfoam_bashrc(
    *,
    bashrc_path: str | Path | None = None,
    base_env: Mapping[str, str] | None = None,
) -> Path | None:
    """The bashrc the caller supplied: ``bashrc_path`` (``--environment-source``),
    else ``OPENFOAM_BASHRC``, else the runtime file's. Nothing is searched for."""
    if bashrc_path:
        return Path(bashrc_path).expanduser()
    env = os.environ if base_env is None else base_env
    named = env.get("OPENFOAM_BASHRC") or configured_openfoam_bashrc(env)
    return Path(named).expanduser() if named else None


def load_openfoam_environment(
    *,
    bashrc_path: str | Path | None = None,
    base_env: Mapping[str, str] | None = None,
    driver_context: Any | None = None,
    timeout_s: float = 20.0,
) -> OpenFOAMEnvironment:
    """Return an environment suitable for strict OpenFOAM execution.

    If no bashrc can be found, return the current environment unchanged so the
    normal preflight diagnostics can report the missing OpenFOAM variables and
    executables.
    """
    env = dict(base_env or os.environ)
    bashrc = supplied_openfoam_bashrc(bashrc_path=bashrc_path, base_env=env)
    if bashrc is None:
        return _configure_plugin_environment(OpenFOAMEnvironment(env=env), driver_context)
    if not bashrc.is_file():
        return OpenFOAMEnvironment(env=env, error=f"OpenFOAM bashrc not found: {bashrc}")

    script = (
        'set +e +u\n'
        'source "$_DRIVER_OPENFOAM_BASHRC" >/dev/null || exit $?\n'
        'export -p > "$_DRIVER_ENV_FILE"'
    )
    env_file = tempfile.NamedTemporaryFile(delete=False)
    err_file = tempfile.NamedTemporaryFile(delete=False)
    env_file.close()
    err_file.close()
    temp_paths = (Path(env_file.name), Path(err_file.name))
    try:
        with open(err_file.name, "wb") as stderr_handle:
            source_env = {
                **env,
                "_DRIVER_OPENFOAM_BASHRC": str(bashrc),
                "_DRIVER_ENV_FILE": env_file.name,
            }
            completed = subprocess.run(
                ("bash", "-c", script),
                env=source_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                timeout=timeout_s,
                check=False,
            )
    except subprocess.TimeoutExpired:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        return OpenFOAMEnvironment(
            env=env,
            bashrc=str(bashrc),
            error=f"source {bashrc} timed out after {timeout_s:g} seconds",
        )
    except OSError as exc:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        return OpenFOAMEnvironment(env=env, bashrc=str(bashrc), error=str(exc))

    if completed.returncode != 0:
        stderr = Path(err_file.name).read_text(errors="replace").strip()
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        return OpenFOAMEnvironment(
            env=env,
            bashrc=str(bashrc),
            error=stderr or f"source {bashrc} exited with {completed.returncode}",
        )

    raw_env = Path(env_file.name).read_text(errors="replace")
    for temp_path in temp_paths:
        temp_path.unlink(missing_ok=True)
    sourced_env = _parse_exported_environment(raw_env)

    sourced = OpenFOAMEnvironment(env=sourced_env, bashrc=str(bashrc))
    return _configure_plugin_environment(sourced, driver_context)


def _configure_plugin_environment(
    environment: OpenFOAMEnvironment,
    driver_context: Any | None,
) -> OpenFOAMEnvironment:
    """Return the sourced environment unchanged; project-specific library
    selection belongs to whichever provider composes with this one, not here.
    ``driver_context`` is kept only for signature stability."""
    return environment


def configure_plugin_environment(
    env: Mapping[str, str],
    driver_context: Any | None,
) -> OpenFOAMEnvironment:
    """Apply a plugin environment contract without sourcing OpenFOAM again."""
    return _configure_plugin_environment(
        OpenFOAMEnvironment(env=dict(env)),
        driver_context,
    )
