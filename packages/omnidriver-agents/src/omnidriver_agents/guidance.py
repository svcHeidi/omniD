"""The guidance an agent receives for a role, resolved from the repository's manifest with each file's hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST = "agent-handbook/guidance-manifest.yaml"


class GuidanceError(ValueError):
    """The manifest names a role or a file that does not exist."""


@dataclass(frozen=True)
class Guidance:
    text: str
    files: tuple[tuple[str, str], ...]


def load_guidance(repo: Path, role: str) -> Guidance:
    """The manifest's ``common`` files, then the role's ``required`` ones, concatenated, each hashed."""
    manifest = yaml.safe_load((repo / MANIFEST).read_text())
    if role not in manifest["roles"]:
        raise GuidanceError(f"{MANIFEST} has no role {role!r}")
    paths = [*manifest["common"], *manifest["roles"][role]["required"]]
    parts, files = [], []
    for relpath in paths:
        path = repo / relpath
        if not path.is_file():
            raise GuidanceError(f"{MANIFEST} lists {relpath}, which does not exist")
        data = path.read_bytes()
        files.append((relpath, hashlib.sha256(data).hexdigest()))
        parts.append(f"<file path=\"{relpath}\">\n{data.decode()}\n</file>")
    return Guidance(text="\n\n".join(parts), files=tuple(files))
