"""Which TorchCor a run uses: the repository's own package, installed editable, read when the plan is made."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import git_identity, tree_digest


def torchcor_solver_builds(env: Mapping[str, str], *, repository: Any) -> tuple[SolverEntry, ...]:
    """``live`` when the stack's ``python3`` imports ``torchcor`` from the repository's ``source``,
    else ``unknown``; nothing without a repository."""
    if repository is None:
        return ()
    source = Path(repository.source).resolve()
    identity = SourceIdentity(repository=str(source), digest=tree_digest(source, sorted(source.rglob("*.py"))),
                              git=git_identity(source))
    python = shutil.which("python3", path=env.get("PATH", ""))
    location = _package_file(python, env) if python else None
    if location is not None and location.resolve().is_relative_to(source):
        build = SolverBuild(name="torchcor", path=location.parent, digest=identity.digest, known="live", source=identity)
    else:
        build = SolverBuild(name="torchcor", path=location.parent if location else None, digest=None, known="unknown")
    return (SolverEntry(solver=repository.plugin, repository=identity, builds=(build,)),)


def _package_file(python: str, env: Mapping[str, str]) -> Path | None:
    try:
        proc = subprocess.run((python, "-c", "import torchcor; print(torchcor.__file__)"),
                              capture_output=True, text=True, env=dict(env), timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.strip()
    return Path(out) if proc.returncode == 0 and out else None
