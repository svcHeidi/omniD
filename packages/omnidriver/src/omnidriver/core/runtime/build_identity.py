"""Which source built what a run uses: content digests, a tree's digest, and git identity."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .provenance import component_for_path


def file_digest(path: Path) -> str | None:
    """``sha256:<hex>`` of ``path``'s bytes, the resume snapshot's content hash; ``None`` when unreadable."""
    path = Path(path)
    component = component_for_path(path, kind="build", relative_to=path.parent)
    return component.digest if component.strength == "content" else None


def tree_digest(root: Path, files: Iterable[Path]) -> str:
    """``sha256:<hex>`` of ``files`` under ``root``, in sorted relative-path order, each as its path and bytes."""
    root = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(Path(path).relative_to(root).as_posix() for path in files):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def git_identity(directory: Path) -> dict[str, Any] | None:
    """``{"commit", "dirty"}`` of the checkout rooted at ``directory``; ``None`` without a usable
    ``directory/.git``. No parent directory is searched."""
    directory = Path(directory)
    if not (directory / ".git").exists():
        return None
    commit = _git(directory, "rev-parse", "HEAD")
    if not commit:
        return None
    status = _git(directory, "status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _git(directory: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(("git", "-C", str(directory), *args),
                              capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None
