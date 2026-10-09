"""TorchCor's key catalogue, as the solver repository's runner describes it (``run_case.py --describe``).

The runner reads the installed TorchCor in TorchCor's own interpreter, so the
catalogue is the solver's, never omniD's. It is cached under the supplied
scratch root by a digest of the runner and the TorchCor source.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.repository import read_repository
from omnidriver.core.scripts import ScriptError, script_argv
from omnidriver.core.specs.paths import SCRATCH_ENV_VAR

#: The solver repository, as ``--repo`` names it. Core hands the key
#: validator, the case rules and the key catalogue no repository, so they
#: find the runner through this supplied variable, read from the environment
#: as the OpenFOAM layer reads its source root.
REPOSITORY_VARIABLE = "TORCHCOR_REPOSITORY"
RUNNER = "run_case.py"
CASE_DOCUMENT = "case.json"

_MEMO: dict[str, dict[str, Any]] = {}


class CatalogError(RuntimeError):
    """The runner could not describe its keys."""


@dataclass(frozen=True)
class Catalog:
    keys: Mapping[str, Mapping[str, Any]]
    ionic_models: Mapping[str, Mapping[str, Any]]
    devices: tuple[str, ...]
    runner: str = RUNNER

    @classmethod
    def from_describe(cls, data: Mapping[str, Any], runner: str = RUNNER) -> "Catalog":
        return cls(keys=data["keys"], ionic_models=data["ionic_models"], devices=tuple(data["devices"]), runner=runner)


def source_digest(runner: Path, source: Path) -> str:
    digest = hashlib.sha256(Path(runner).read_bytes())
    for path in sorted(Path(source).rglob("*.py")):
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def describe(runner: Path, source: Path, env: Mapping[str, str], scratch_root: Path | None) -> dict[str, Any]:
    """``runner --describe`` under the ``python3`` on ``env``'s PATH, cached by :func:`source_digest`."""
    digest = source_digest(runner, source)
    if digest in _MEMO:
        return _MEMO[digest]
    cache = Path(scratch_root) / "torchcor-describe" / f"{digest}.json" if scratch_root is not None else None
    if cache is not None and cache.is_file():
        _MEMO[digest] = json.loads(cache.read_text())
        return _MEMO[digest]
    try:
        command = (*script_argv(Path(runner), env), "--describe")
    except ScriptError as exc:
        raise CatalogError(str(exc)) from exc
    found = subprocess.run(command, capture_output=True, text=True, env=dict(env), timeout=600)
    if found.returncode != 0:
        raise CatalogError(f"{' '.join(command)} exited {found.returncode}: {found.stderr.strip()[-600:]}")
    data = json.loads(found.stdout)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    _MEMO[digest] = data
    return data


def supplied_runner() -> tuple[Path, Path] | None:
    """The runner and TorchCor source of the supplied repository, or ``None``."""
    supplied = os.environ.get(REPOSITORY_VARIABLE)
    if not supplied:
        return None
    repository = read_repository(Path(supplied).expanduser())
    return repository.scripts / RUNNER, repository.source


def supplied_catalog() -> Catalog | None:
    located = supplied_runner()
    if located is None:
        return None
    runner, source = located
    scratch = os.environ.get(SCRATCH_ENV_VAR)
    data = describe(runner, source, os.environ, Path(scratch).expanduser() if scratch else None)
    return Catalog.from_describe(data, runner=str(runner))
