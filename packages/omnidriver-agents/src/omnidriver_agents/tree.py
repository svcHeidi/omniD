"""A trial's native tree: exported from git so it holds only committed files, and digested before and after."""

from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


def export_tree(git_dir: Path, ref: str, dest: Path) -> str:
    """Write ``git archive <ref>`` of ``git_dir`` into ``dest``; return the commit it resolved to."""
    commit = subprocess.run(["git", "-C", str(git_dir), "rev-parse", f"{ref}^{{commit}}"],
                            check=True, capture_output=True, text=True).stdout.strip()
    archive = subprocess.run(["git", "-C", str(git_dir), "archive", commit], check=True, capture_output=True).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    return commit


def digest_tree(root: Path) -> str:
    """SHA-256 over every path under ``root`` and its content; times are ignored."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relpath = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            digest.update(b"L" + relpath + b"\0" + str(path.readlink()).encode() + b"\0")
        elif path.is_file():
            digest.update(b"F" + relpath + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
