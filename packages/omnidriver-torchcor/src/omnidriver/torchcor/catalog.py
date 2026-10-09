"""TorchCor's key catalogue and case rules, as the solver repository's runner states them.

The runner is the one in the repository the stack was selected from
(``driver_context.repository``), run under the stack's ``python3``: it reads
the installed TorchCor in TorchCor's own interpreter, so the keys
(``--describe``) and the rules a case.json breaks (``--check``) are the
solver's, never omniD's. The catalogue is cached under the supplied scratch
root by :func:`runner_digest`.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.environment_connection import load_environment
from omnidriver.core.scripts import ScriptError, script_argv
from omnidriver.core.specs.paths import SCRATCH_ENV_VAR

RUNNER = "run_case.py"
CASE_DOCUMENT = "case.json"

_MEMO: dict[str, dict[str, Any]] = {}
_CHECKED: dict[tuple[str, str], list[dict[str, str]]] = {}


class CatalogError(RuntimeError):
    """The runner could not describe its keys or judge a case."""


@dataclass(frozen=True)
class Catalog:
    keys: Mapping[str, Mapping[str, Any]]
    ionic_models: Mapping[str, Mapping[str, Any]]
    runner: str = RUNNER

    @classmethod
    def from_describe(cls, data: Mapping[str, Any], runner: str = RUNNER) -> "Catalog":
        return cls(keys=data["keys"], ionic_models=data["ionic_models"], runner=runner)


#: The ``torch`` package directory, ``""`` with none, per interpreter path.
_TORCH: dict[str, str] = {}


def _torch_directory(python: str, env: Mapping[str, str]) -> str:
    """Where ``python`` finds ``torch``, located without importing it."""
    if python not in _TORCH:
        found = subprocess.run(
            (python, "-c", "import importlib.util as u; s = u.find_spec('torch'); print(s.submodule_search_locations[0] if s else '')"),
            capture_output=True, text=True, env=dict(env), timeout=60,
        )
        if found.returncode != 0:
            raise CatalogError(f"{python} cannot look for torch: {found.stderr.strip()[-600:]}")
        _TORCH[python] = found.stdout.strip()
    return _TORCH[python]


def runner_digest(runner: Path, source: Path, env: Mapping[str, str]) -> str:
    """What the runner's answers depend on: its bytes, the TorchCor source, the
    ``python3`` that runs it (the path on PATH and, since a venv's is a link,
    the interpreter it resolves to), that interpreter's ``torch/version.py``,
    and the host, whose devices ``--describe`` lists."""
    try:
        python = script_argv(Path(runner), env)[0]
    except ScriptError as exc:
        raise CatalogError(str(exc)) from exc
    torch = _torch_directory(python, env)
    version = Path(torch) / "version.py" if torch else None
    digest = hashlib.sha256(Path(runner).read_bytes())
    for path in sorted(Path(source).rglob("*.py")):
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    for part in (python, os.path.realpath(python), str(version), platform.node()):
        digest.update(b"\0" + part.encode())
    digest.update(b"\0" + (version.read_bytes() if version is not None and version.is_file() else b""))
    return digest.hexdigest()


def _run(runner: Path, env: Mapping[str, str], *arguments: str) -> Any:
    try:
        command = (*script_argv(Path(runner), env), *arguments)
    except ScriptError as exc:
        raise CatalogError(str(exc)) from exc
    found = subprocess.run(command, capture_output=True, text=True, env=dict(env), timeout=600)
    if found.returncode != 0:
        raise CatalogError(f"{' '.join(command)} exited {found.returncode}: {found.stderr.strip()[-600:]}")
    return json.loads(found.stdout)


def describe(runner: Path, source: Path, env: Mapping[str, str], scratch_root: Path | None) -> dict[str, Any]:
    """``runner --describe`` under the ``python3`` on ``env``'s PATH, cached by :func:`runner_digest`."""
    digest = runner_digest(runner, source, env)
    if digest in _MEMO:
        return _MEMO[digest]
    cache = Path(scratch_root) / "torchcor-describe" / f"{digest}.json" if scratch_root is not None else None
    if cache is not None and cache.is_file():
        _MEMO[digest] = json.loads(cache.read_text())
        return _MEMO[digest]
    data = _run(runner, env, "--describe")
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    _MEMO[digest] = data
    return data


def check(runner: Path, source: Path, env: Mapping[str, str], case: Path) -> list[dict[str, str]]:
    """``runner --check case``: each rule the case breaks, as ``{key, rule, message}``.
    Remembered in-process by the runner's digest and the case's bytes: a check takes
    seconds, and a plan, a commit and a run judge the same case."""
    key = (runner_digest(runner, source, env), hashlib.sha256(Path(case).read_bytes()).hexdigest())
    if key not in _CHECKED:
        _CHECKED[key] = _run(runner, env, "--check", str(case))["refusals"]
    return _CHECKED[key]


def runner_of(driver_context: Any) -> tuple[Path, Path, dict[str, str]] | None:
    """The runner, the TorchCor source and the stack's environment, or ``None`` when the stack was selected by ``--plugin`` alone."""
    repository = driver_context.repository
    if repository is None:
        return None
    return repository.scripts / RUNNER, repository.source, load_environment(driver_context, None)


def repository_catalog(driver_context: Any) -> Catalog | None:
    """The catalogue of the context's repository's runner, or ``None`` with no repository."""
    located = runner_of(driver_context)
    if located is None:
        return None
    runner, source, env = located
    scratch = os.environ.get(SCRATCH_ENV_VAR)
    return Catalog.from_describe(describe(runner, source, env, Path(scratch).expanduser() if scratch else None), runner=str(runner))
