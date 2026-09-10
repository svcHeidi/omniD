"""Snapshot and archive a declared generated-output tree.

Core owns the snapshot/diff/collision mechanism. The active environment
declares which relative tree is generated (if any); this module therefore
accepts an already-resolved root and has no solver directory conventions.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path


class OutputCollisionError(Exception):
    """Two attempts produced different content at one archived path."""


def snapshot_output_tree(root: Path) -> dict[str, tuple[float, int]]:
    """Record ``(mtime, size)`` for every file below a declared output root."""
    root = Path(root)
    if not root.is_dir():
        return {}
    snapshot: dict[str, tuple[float, int]] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            stat = path.stat()
            snapshot[str(path.relative_to(root))] = (stat.st_mtime, stat.st_size)
    return snapshot


def collect_new_output_tree(
    root: Path,
    before: dict[str, tuple[float, int]],
    destination_dir: Path,
    *,
    label: str = "",
) -> list[Path]:
    """Archive files new or changed below one declared generated-output tree.

    ``destination_dir`` must already be unique to the case. Repeated identical
    content is accepted; different content at the same destination is refused
    so a retry cannot silently overwrite attributable evidence.
    """
    root = Path(root)
    destination_root = Path(destination_dir)
    if not root.is_dir():
        return []

    archived: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            source = Path(dirpath) / filename
            relpath = str(source.relative_to(root))
            stat = source.stat()
            if before.get(relpath) == (stat.st_mtime, stat.st_size):
                continue
            destination = destination_root / relpath
            if destination.exists():
                if filecmp.cmp(source, destination, shallow=False):
                    continue
                raise OutputCollisionError(
                    f"{relpath!r} already exists in {destination_root} "
                    f"({label or 'no label given'}) with different content -- "
                    "likely a retry racing a partial prior attempt. Refusing to overwrite."
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            archived.append(destination)
    return archived
